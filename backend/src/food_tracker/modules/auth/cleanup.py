"""Expired refresh history is retained until the absolute session expiry."""

from datetime import timedelta

from sqlalchemy import delete, exists, select

from food_tracker.modules.auth.models import AuthRateLimit, AuthSession, EmailChallenge, EmailOutbox
from food_tracker.modules.users.models import User


async def cleanup(factory, now):
    async with factory() as db, db.begin():
        await db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
        await db.execute(delete(EmailOutbox).where(EmailOutbox.expires_at <= now))
        await db.execute(
            delete(EmailChallenge).where(EmailChallenge.expires_at < now - timedelta(days=1))
        )
        await db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at <= now))
        active = exists(
            select(EmailChallenge.id).where(
                EmailChallenge.user_id == User.id,
                EmailChallenge.consumed_at.is_(None),
                EmailChallenge.expires_at > now,
            )
        )
        await db.execute(
            delete(User).where(
                User.email_verified_at.is_(None), User.created_at < now - timedelta(days=7), ~active
            )
        )
