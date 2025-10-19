from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240801_02"
down_revision = "20240801_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "weekly_insights",
        sa.Column(
            "entries_by_day",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.execute(
        "UPDATE weekly_insights SET entries_by_day = '[]' WHERE entries_by_day IS NULL"
    )


def downgrade() -> None:
    op.drop_column("weekly_insights", "entries_by_day")
