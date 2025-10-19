"""Create journal, emotions, settings tables.

Revision ID: 20240715_01
Revises: 
Create Date: 2024-07-15 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240715_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("entry_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_journal_user_id", "journal", ["user_id"])

    op.create_table(
        "emotions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("emotion_code", sa.String(length=50), nullable=False),
        sa.Column("intensity", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_emotions_user_id", "emotions", ["user_id"])

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_settings_key"),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index("ix_emotions_user_id", table_name="emotions")
    op.drop_table("emotions")
    op.drop_index("ix_journal_user_id", table_name="journal")
    op.drop_table("journal")
