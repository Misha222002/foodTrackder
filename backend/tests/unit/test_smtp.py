import ssl
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from food_tracker.core.config import Settings
from food_tracker.modules.auth.mail import SmtpMailer


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["ssl", "starttls"])
async def test_external_smtp_verifies_certificate_before_sending_credentials(monkeypatch, mode):
    settings = Settings(
        _env_file=None,
        smtp_host="smtp.example.org",
        smtp_port=465 if mode == "ssl" else 587,
        smtp_ssl=mode == "ssl",
        smtp_starttls=mode == "starttls",
        smtp_username="sender@example.org",
        smtp_password="app-password",
        smtp_sender="Ем по плану <sender@example.org>",
    )
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.noop.return_value = (250, b"OK")
    constructor = MagicMock(return_value=connection)
    other = MagicMock(side_effect=AssertionError("Unexpected transport fallback"))
    module = "food_tracker.modules.auth.mail.smtplib."
    monkeypatch.setattr(module + ("SMTP_SSL" if mode == "ssl" else "SMTP"), constructor)
    monkeypatch.setattr(module + ("SMTP" if mode == "ssl" else "SMTP_SSL"), other)
    mailer = SmtpMailer(settings)
    await mailer.send("recipient@example.org", "Код", "Test body")
    context = (
        constructor.call_args.kwargs["context"]
        if mode == "ssl"
        else connection.starttls.call_args.kwargs["context"]
    )
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    connection.login.assert_called_once_with("sender@example.org", "app-password")
    message = connection.send_message.call_args.args[0]
    assert str(message["From"]) == settings.smtp_sender
    if mode == "starttls":
        names = [call[0] for call in connection.mock_calls]
        assert names.index("starttls") < names.index("login") < names.index("send_message")
    await mailer.check_connection()
    connection.noop.assert_called_once()


@pytest.mark.anyio
async def test_invalid_smtp_certificate_never_falls_back_to_plaintext(monkeypatch):
    settings = Settings(_env_file=None, smtp_host="smtp.example.org", smtp_ssl=True, smtp_port=465)
    monkeypatch.setattr(
        "food_tracker.modules.auth.mail.smtplib.SMTP_SSL",
        MagicMock(side_effect=ssl.SSLCertVerificationError("invalid cert")),
    )
    plaintext = MagicMock()
    monkeypatch.setattr("food_tracker.modules.auth.mail.smtplib.SMTP", plaintext)
    with pytest.raises(ssl.SSLCertVerificationError):
        await SmtpMailer(settings).send("recipient@example.org", "Test", "Test")
    plaintext.assert_not_called()


@pytest.mark.parametrize(
    "values",
    [
        {"smtp_host": "smtp.example.org"},
        {"smtp_ssl": True, "smtp_starttls": True},
        {"smtp_username": "sender@example.org"},
    ],
)
def test_invalid_smtp_configuration_fails_without_exposing_secrets(values):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert "input_value" not in str(error.value)
