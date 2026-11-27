from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FOOD_TRACKER_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: PostgresDsn = (
        "postgresql+psycopg://food_tracker:food_tracker@127.0.0.1:5432/food_tracker"
    )

    access_jwt_secret: SecretStr | None = None
    refresh_jwt_secret: SecretStr | None = None
    code_hmac_secret: SecretStr | None = None
    csrf_secret: SecretStr | None = None
    mail_encryption_key: SecretStr | None = None
    jwt_issuer: str = "food-tracker"
    access_audience: str = "food-tracker-api"
    refresh_audience: str = "food-tracker-refresh"
    access_ttl_seconds: int = Field(default=900, ge=60)
    session_ttl_seconds: int = Field(default=2592000, ge=900)
    csrf_ttl_seconds: int = Field(default=86400, ge=60)
    code_ttl_seconds: int = Field(default=600, ge=60)
    resend_interval_seconds: int = Field(default=60, ge=1)
    code_max_attempts: int = Field(default=5, ge=1, le=10)
    code_send_account_limit: int = Field(default=10, ge=1)
    code_send_ip_limit: int = Field(default=30, ge=1)
    code_attempt_account_limit: int = Field(default=20, ge=1)
    code_attempt_ip_limit: int = Field(default=100, ge=1)
    login_account_limit: int = Field(default=10, ge=1)
    login_ip_limit: int = Field(default=50, ge=1)
    auth_request_ip_limit: int = Field(default=120, ge=1)
    auth_min_response_seconds: float = Field(default=0.25, ge=0)
    auth_allowed_origins: list[str] = ["https://localhost:5173", "https://127.0.0.1:5173"]
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_ssl: bool = False
    smtp_sender: str = "Ем по плану <no-reply@food-tracker.local>"
    mail_worker_enabled: bool = True
    mail_poll_seconds: float = Field(default=5, ge=0.1)

    @model_validator(mode="after")
    def validate_auth_keys(self):
        values = [
            v.get_secret_value()
            for v in (
                self.access_jwt_secret,
                self.refresh_jwt_secret,
                self.code_hmac_secret,
                self.csrf_secret,
            )
            if v is not None
        ]
        if any(len(v.encode()) < 32 for v in values) or len(set(values)) != len(values):
            raise ValueError("Auth keys must be distinct and contain at least 32 bytes")
        if self.mail_encryption_key:
            if self.mail_encryption_key.get_secret_value() in values:
                raise ValueError("Mail encryption requires a separate key")
            from cryptography.fernet import Fernet

            try:
                Fernet(self.mail_encryption_key.get_secret_value().encode())
            except (ValueError, TypeError) as error:
                raise ValueError("Invalid mail encryption key") from error
        if any(origin.endswith("/") or origin == "*" for origin in self.auth_allowed_origins):
            raise ValueError("Use explicit allowed origins without trailing slashes")
        return self

    @model_validator(mode="after")
    def validate_smtp_transport(self):
        if self.smtp_ssl and self.smtp_starttls:
            raise ValueError("Choose SMTP SSL or STARTTLS, not both")
        if self.smtp_host not in ("localhost", "127.0.0.1", "::1"):
            if not (self.smtp_ssl or self.smtp_starttls):
                raise ValueError("External SMTP requires SSL or STARTTLS")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP username and password must be configured together")
        return self

    @field_validator("database_url")
    @classmethod
    def require_async_driver(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+psycopg":
            raise ValueError("Use the postgresql+psycopg driver")
        return value
