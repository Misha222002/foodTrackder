"""Durable encrypted outbox. SMTP runs after the leasing transaction has committed."""

import asyncio
import json
import smtplib
import ssl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from email.message import EmailMessage
from typing import Protocol
from uuid import UUID

import anyio
from cryptography.fernet import Fernet
from sqlalchemy import or_, select

from food_tracker.core.security import secret
from food_tracker.modules.auth.models import EmailOutbox


class Mailer(Protocol):
    async def send(self, recipient: str, subject: str, body: str) -> None: ...


@dataclass
class MemoryMailer:
    messages: list[tuple[str, str, str]]

    async def send(self, recipient, subject, body):
        self.messages.append((recipient, subject, body))


class SmtpMailer:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def _connection(self):
        settings = self.settings
        options = {"timeout": 10, "local_hostname": "food-tracker.local"}
        if settings.smtp_ssl:
            connection = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                context=ssl.create_default_context(),
                **options,
            )
        else:
            connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, **options)
        with connection as smtp:
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, secret(settings, "smtp_password"))
            yield smtp

    async def check_connection(self):
        def check():
            with self._connection() as smtp:
                status, _ = smtp.noop()
                if status != 250:
                    raise smtplib.SMTPResponseException(status, b"SMTP check failed")

        await anyio.to_thread.run_sync(check)

    async def send(self, recipient, subject, body):
        def deliver():
            message = EmailMessage()
            message["From"] = self.settings.smtp_sender
            message["To"] = recipient
            message["Subject"] = subject
            message.set_content(body)
            with self._connection() as smtp:
                smtp.send_message(message)

        await anyio.to_thread.run_sync(deliver)


def enqueue(
    session,
    settings,
    now,
    *,
    user_id: UUID | None,
    recipient: str | None,
    subject: str,
    body: str,
    challenge=None,
):
    encrypted = (
        Fernet(secret(settings, "mail_encryption_key").encode())
        .encrypt(json.dumps({"subject": subject, "body": body}).encode())
        .decode()
    )
    session.add(
        EmailOutbox(
            user_id=user_id,
            challenge_id=challenge.id if challenge else None,
            recipient=recipient,
            encrypted_payload=encrypted,
            available_at=now,
            expires_at=challenge.expires_at if challenge else now + timedelta(days=1),
        )
    )


async def deliver_pending(factory, settings, mailer: Mailer, clock, limit=20):
    for _ in range(limit):
        now = clock()
        async with factory() as session, session.begin():
            row = await session.scalar(
                select(EmailOutbox)
                .where(
                    EmailOutbox.sent_at.is_(None),
                    EmailOutbox.available_at <= now,
                    EmailOutbox.expires_at > now,
                    or_(EmailOutbox.leased_until.is_(None), EmailOutbox.leased_until <= now),
                )
                .order_by(EmailOutbox.available_at, EmailOutbox.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                return
            row.leased_until = now + timedelta(seconds=30)
            row.attempts += 1
            row_id, recipient, encrypted = row.id, row.recipient, row.encrypted_payload
        try:
            payload = json.loads(
                Fernet(secret(settings, "mail_encryption_key").encode()).decrypt(encrypted.encode())
            )
            if recipient:
                await mailer.send(recipient, payload["subject"], payload["body"])
        except Exception:
            # Do not log SMTP exception text: providers may include message/credentials.
            async with factory() as session, session.begin():
                row = await session.get(EmailOutbox, row_id, with_for_update=True)
                if row:
                    row.available_at = clock() + timedelta(
                        seconds=min(300, 5 * 2 ** min(row.attempts, 6))
                    )
                    row.leased_until = None
        else:
            async with factory() as session, session.begin():
                row = await session.get(EmailOutbox, row_id, with_for_update=True)
                if row:
                    row.sent_at = clock()
                    row.leased_until = None
                    # Codes are no longer needed in the outbox after delivery.
                    row.encrypted_payload = ""


async def mail_worker(factory, settings, mailer, clock):
    from food_tracker.modules.auth.cleanup import cleanup

    last_cleanup = None
    while True:
        try:
            await deliver_pending(factory, settings, mailer, clock)
            if last_cleanup is None or clock() - last_cleanup >= timedelta(hours=1):
                await cleanup(factory, clock())
                last_cleanup = clock()
        except Exception:
            # A temporarily unavailable database must not permanently stop delivery.
            pass
        await asyncio.sleep(settings.mail_poll_seconds)
