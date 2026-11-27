"""accounts sessions and email outbox

Revision ID: 0002_accounts
Revises: 0001_baseline
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_accounts"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("bucket", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket", name=op.f("pk_auth_rate_limits")),
    )
    op.create_index(
        op.f("ix_auth_rate_limits_expires_at"), "auth_rate_limits", ["expires_at"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("role", sa.String(length=10), server_default="USER", nullable=False),
        sa.Column("display_name", sa.String(length=100), server_default="", nullable=False),
        sa.Column("timezone", sa.String(length=100), server_default="UTC", nullable=False),
        sa.Column("meal_times", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('USER', 'ADMIN')", name=op.f("ck_users_valid_role")),
        sa.CheckConstraint("revision > 0", name=op.f("ck_users_positive_revision")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index(
        op.f("ix_auth_sessions_expires_at"), "auth_sessions", ["expires_at"], unique=False
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "email_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("account_key", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name=op.f("ck_email_challenges_valid_purpose"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_email_challenges_nonnegative_attempts")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_challenges")),
    )
    op.create_index(
        op.f("ix_email_challenges_expires_at"), "email_challenges", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_email_challenges_user_id"), "email_challenges", ["user_id"], unique=False
    )
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("challenge_id", sa.Uuid(), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["challenge_id"],
            ["email_challenges.id"],
            name=op.f("fk_email_outbox_challenge_id_email_challenges"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_outbox_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
    )
    op.create_index(
        op.f("ix_email_outbox_available_at"), "email_outbox", ["available_at"], unique=False
    )
    op.create_index(
        op.f("ix_email_outbox_challenge_id"), "email_outbox", ["challenge_id"], unique=False
    )
    op.create_index(op.f("ix_email_outbox_user_id"), "email_outbox", ["user_id"], unique=False)
    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_jti", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            name=op.f("fk_refresh_tokens_session_id_auth_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_refresh_tokens")),
    )
    op.create_index(
        op.f("ix_refresh_tokens_expires_at"), "refresh_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_expires_at"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_email_outbox_user_id"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_challenge_id"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_available_at"), table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index(op.f("ix_email_challenges_user_id"), table_name="email_challenges")
    op.drop_index(op.f("ix_email_challenges_expires_at"), table_name="email_challenges")
    op.drop_table("email_challenges")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_expires_at"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_index(op.f("ix_auth_rate_limits_expires_at"), table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
