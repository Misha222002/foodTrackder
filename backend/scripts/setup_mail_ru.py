"""Configure the approved sender after a successful SMTP login, without printing secrets."""

import asyncio
import getpass
import smtplib
import ssl
import sys
from pathlib import Path

from food_tracker.core.config import Settings
from food_tracker.core.local_env import update_env
from food_tracker.modules.auth.mail import SmtpMailer

SENDER = "em.poplanu@mail.ru"
BACKEND = Path(__file__).resolve().parents[1]


async def main():
    if not sys.stdin.isatty():
        raise SystemExit("Запустите команду в своём терминале: пароль вводится скрыто.")
    password = getpass.getpass("Пароль для внешнего приложения Mail.ru (ввод скрыт): ")
    if not password:
        raise SystemExit("Пароль не введён. Настройки не изменены.")
    values = {
        "FOOD_TRACKER_SMTP_HOST": "smtp.mail.ru",
        "FOOD_TRACKER_SMTP_PORT": "465",
        "FOOD_TRACKER_SMTP_SSL": "true",
        "FOOD_TRACKER_SMTP_STARTTLS": "false",
        "FOOD_TRACKER_SMTP_USERNAME": SENDER,
        "FOOD_TRACKER_SMTP_PASSWORD": password,
        "FOOD_TRACKER_SMTP_SENDER": f"Ем по плану <{SENDER}>",
    }
    settings = Settings(
        _env_file=BACKEND / ".env",
        smtp_host="smtp.mail.ru",
        smtp_port=465,
        smtp_ssl=True,
        smtp_starttls=False,
        smtp_username=SENDER,
        smtp_password=password,
        smtp_sender=f"Ем по плану <{SENDER}>",
    )
    try:
        await SmtpMailer(settings).check_connection()
    except smtplib.SMTPAuthenticationError:
        raise SystemExit(
            "Mail.ru не принял пароль. Проверьте пароль приложения с правом отправки. "
            "Настройки не изменены."
        ) from None
    except ssl.SSLCertVerificationError:
        raise SystemExit("Сертификат SMTP не прошёл проверку. Настройки не изменены.") from None
    except (OSError, smtplib.SMTPException):
        raise SystemExit(
            "Нет подключения к SMTP Mail.ru. Проверьте сеть и настройки ящика. "
            "Настройки не изменены."
        ) from None
    update_env(BACKEND / ".env", values)
    update_env(BACKEND.parent / "frontend/.env", {"VITE_DEV_MAILBOX_URL": ""})
    print(f"SMTP Mail.ru: вход выполнен, отправитель {SENDER} сохранён локально.")
    print("Пароль не выводился. Перезапустите backend и frontend для применения настроек.")
    print("Письма этой командой не отправлялись. Запросите новый код в приложении.")


if __name__ == "__main__":
    asyncio.run(main())
