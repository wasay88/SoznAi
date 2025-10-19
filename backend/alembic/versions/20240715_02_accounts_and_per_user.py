"""Add users, sessions, and per-user constraints.

Revision ID: 20240715_02
Revises: 20240715_01
Create Date: 2024-07-15 12:00:00
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240715_02"
down_revision = "20240715_01"
branch_labels = None
depends_on = None

LEGACY_USER_ID = 1


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_tg_id", "users", ["tg_id"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)

    connection = op.get_bind()
    now_value = datetime.utcnow()
    connection.execute(
        sa.text(
            "INSERT INTO users (id, tg_id, email, created_at) VALUES (:id, NULL, NULL, :created) "
            "ON CONFLICT(id) DO NOTHING"
        ),
        {"id": LEGACY_USER_ID, "created": now_value},
    )

    connection.execute(
        sa.text("UPDATE journal SET user_id = :legacy WHERE user_id IS NULL"),
        {"legacy": LEGACY_USER_ID},
    )
    connection.execute(
        sa.text("UPDATE emotions SET user_id = :legacy WHERE user_id IS NULL"),
        {"legacy": LEGACY_USER_ID},
    )

    with op.batch_alter_table("journal") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_index("ix_journal_user_id")
        batch_op.create_foreign_key(
            "fk_journal_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_journal_user_id_created_at",
            ["user_id", "created_at"],
        )

    with op.batch_alter_table("emotions") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_index("ix_emotions_user_id")
        batch_op.create_foreign_key(
            "fk_emotions_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_emotions_user_id_created_at",
            ["user_id", "created_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("emotions") as batch_op:
        batch_op.drop_index("ix_emotions_user_id_created_at")
        batch_op.drop_constraint("fk_emotions_user_id_users", type_="foreignkey")
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_index("ix_emotions_user_id", ["user_id"])

    with op.batch_alter_table("journal") as batch_op:
        batch_op.drop_index("ix_journal_user_id_created_at")
        batch_op.drop_constraint("fk_journal_user_id_users", type_="foreignkey")
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch_op.create_index("ix_journal_user_id", ["user_id"])

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_users_tg_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
