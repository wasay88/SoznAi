"""Admin controls tables and usage source column"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20240715_04"
down_revision = "20240715_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add source column to usage_stats if missing
    with op.batch_alter_table("usage_stats", recreate="auto") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=20), nullable=False, server_default="unknown")
        )

    op.create_table(
        "model_switches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_model_switches_created_at", "model_switches", ["created_at"], unique=False)

    op.create_table(
        "ai_limits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("soft_limit", sa.Float(), nullable=False),
        sa.Column("hard_limit", sa.Float(), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_limits_created_at", "ai_limits", ["created_at"], unique=False)

    # Snapshot existing settings as initial history entries when present
    conn = op.get_bind()
    settings_table = sa.table(
        "settings",
        sa.column("key", sa.String()),
        sa.column("value", sa.Text()),
    )
    mode_value = conn.execute(
        sa.select(settings_table.c.value).where(settings_table.c.key == "ai_router_mode")
    ).scalar()
    if mode_value:
        conn.execute(
            sa.table(
                "model_switches",
                sa.column("mode", sa.String()),
                sa.column("actor", sa.String()),
            ).insert(),
            {"mode": mode_value, "actor": "bootstrap"},
        )

    soft_value = conn.execute(
        sa.select(settings_table.c.value).where(settings_table.c.key == "ai_soft_limit")
    ).scalar()
    hard_value = conn.execute(
        sa.select(settings_table.c.value).where(settings_table.c.key == "ai_hard_limit")
    ).scalar()
    if soft_value and hard_value:
        conn.execute(
            sa.table(
                "ai_limits",
                sa.column("soft_limit", sa.Float()),
                sa.column("hard_limit", sa.Float()),
                sa.column("actor", sa.String()),
            ).insert(),
            {
                "soft_limit": float(soft_value),
                "hard_limit": float(hard_value),
                "actor": "bootstrap",
            },
        )


def downgrade() -> None:
    op.drop_index("ix_ai_limits_created_at", table_name="ai_limits")
    op.drop_table("ai_limits")
    op.drop_index("ix_model_switches_created_at", table_name="model_switches")
    op.drop_table("model_switches")

    with op.batch_alter_table("usage_stats", recreate="auto") as batch_op:
        batch_op.drop_column("source")
