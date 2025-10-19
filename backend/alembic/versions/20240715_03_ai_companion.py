"""Add AI usage, cache and insights tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240715_03"
down_revision = "20240715_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ts", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usd_cost", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_usage_stats_ts", "usage_stats", ["ts"], unique=False)

    op.create_table(
        "prompt_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cache_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usd_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("cache_key", name="uq_prompt_cache_key"),
    )
    op.create_index("ix_prompt_cache_created_at", "prompt_cache", ["created_at"], unique=False)

    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "day", name="uq_insights_user_day"),
    )
    op.create_index("ix_insights_user_id", "insights", ["user_id"], unique=False)
    op.create_index("ix_insights_day", "insights", ["day"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_insights_day", table_name="insights")
    op.drop_index("ix_insights_user_id", table_name="insights")
    op.drop_table("insights")
    op.drop_index("ix_prompt_cache_created_at", table_name="prompt_cache")
    op.drop_table("prompt_cache")
    op.drop_index("ix_usage_stats_ts", table_name="usage_stats")
    op.drop_table("usage_stats")
