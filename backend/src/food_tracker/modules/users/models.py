from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from food_tracker.db.base import Base

DEFAULT_MEAL_TIMES = {"breakfast": "08:00", "lunch": "13:00", "dinner": "19:00", "snack": "16:00"}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ADMIN')", name="valid_role"),
        CheckConstraint("revision > 0", name="positive_revision"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(String(10), default="USER", server_default="USER")
    display_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    timezone: Mapped[str] = mapped_column(String(100), default="UTC", server_default="UTC")
    meal_times: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=lambda: DEFAULT_MEAL_TIMES.copy()
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
