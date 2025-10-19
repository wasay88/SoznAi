from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240801_01"
down_revision = "20240715_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_insights",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("mood_avg", sa.Float(), nullable=True),
        sa.Column("mood_volatility", sa.Float(), nullable=True),
        sa.Column("top_emotions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("journal_wordcloud", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("days_with_entries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entries_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_model", sa.String(length=100), nullable=True),
        sa.Column("summary_source", sa.String(length=32), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "week_start", name="uq_weekly_insights_user_week"),
    )
    op.create_index("ix_weekly_insights_user", "weekly_insights", ["user_id"], unique=False)
    op.create_index("ix_weekly_insights_week", "weekly_insights", ["week_start"], unique=False)



def downgrade() -> None:
    op.drop_index("ix_weekly_insights_week", table_name="weekly_insights")
    op.drop_index("ix_weekly_insights_user", table_name="weekly_insights")
    op.drop_table("weekly_insights")
