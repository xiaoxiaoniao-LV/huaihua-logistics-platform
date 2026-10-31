"""alert rules

Revision ID: 0002_alert_rules
Revises: 0001_initial
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_alert_rules"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("resource_id", sa.BigInteger(), nullable=False),
        sa.Column("temp_min", sa.Float(), nullable=False, server_default="-30"),
        sa.Column("temp_max", sa.Float(), nullable=False, server_default="-5"),
        sa.Column("humidity_max", sa.Float(), nullable=False, server_default="90"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_resource_id", "alert_rules", ["resource_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_alert_rules_resource_id", table_name="alert_rules")
    op.drop_table("alert_rules")
