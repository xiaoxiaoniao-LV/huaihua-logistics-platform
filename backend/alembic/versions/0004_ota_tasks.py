"""ota tasks

Revision ID: 0004_ota_tasks
Revises: 0003_audit_logs
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_ota_tasks"
down_revision: Union[str, None] = "0003_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "iot_devices",
        sa.Column("firmware_version", sa.String(length=20), nullable=False,
                  server_default="1.0.0"),
    )
    op.create_table(
        "ota_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("from_version", sa.String(length=20), nullable=True),
        sa.Column("target_version", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ota_tasks_device_id", "ota_tasks", ["device_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ota_tasks_device_id", table_name="ota_tasks")
    op.drop_table("ota_tasks")
    op.drop_column("iot_devices", "firmware_version")
