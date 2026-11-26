from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOOD_TRACKER_", env_file=".env", extra="ignore")

    database_url: PostgresDsn = (
        "postgresql+psycopg://food_tracker:food_tracker@127.0.0.1:5432/food_tracker"
    )

    @field_validator("database_url")
    @classmethod
    def require_async_driver(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+psycopg":
            raise ValueError("Use the postgresql+psycopg driver")
        return value
