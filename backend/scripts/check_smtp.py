"""Check the configured SMTP connection; send a test only with an explicit recipient."""

import argparse
import asyncio
import smtplib
import ssl

from pydantic import EmailStr, TypeAdapter

from food_tracker.core.config import Settings
from food_tracker.modules.auth.mail import SmtpMailer


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send-test-to", type=lambda value: str(TypeAdapter(EmailStr).validate_python(value))
    )
    args = parser.parse_args()
    try:
        settings = Settings()
        mailer = SmtpMailer(settings)
        await mailer.check_connection()
        print("SMTP connection and configured authentication: OK.")
        if args.send_test_to:
            await mailer.send(
                args.send_test_to,
                "Проверка почты Ем по плану",
                "Это проверочное письмо Ем по плану. Ответ не требуется. "
                "Следующим шагом запросите новый код в приложении.",
            )
            print("Test message accepted by SMTP. Check the inbox and spam folder.")
    except smtplib.SMTPAuthenticationError:
        raise SystemExit(
            "SMTP authentication failed. Check the app password and account SMTP settings."
        ) from None
    except ssl.SSLCertVerificationError:
        raise SystemExit(
            "SMTP certificate verification failed. TLS verification remains enabled."
        ) from None
    except (OSError, smtplib.SMTPException):
        raise SystemExit(
            "SMTP connection or delivery failed. Check host, port, TLS and provider settings."
        ) from None


if __name__ == "__main__":
    asyncio.run(main())
