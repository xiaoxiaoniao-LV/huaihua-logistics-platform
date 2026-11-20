"""ota rollout: batches / stage

Revision ID: 0006_ota_rollout
Revises: 0005_platform_v2
Create Date: 2026-11-18

说明：
- 新增 ota_batches 记录灰度/全量/回滚批次；
- ota_tasks 增加 batch_id / stage，便于按批次统计与续发/回滚。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_ota_rollout"
down_revision: Union[str, None] = "0005_platform_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ota_batches",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("target_version", sa.String(length=20), nullable=False),
        sa.Column("space_id", sa.BigInteger(), nullable=True),
        sa.Column("device_ids", sa.Text(), nullable=True),
        sa.Column("rollout_percent", sa.BigInteger(), nullable=False,
                  server_default="100"),
        sa.Column("stage", sa.String(length=10), nullable=False,
                  server_default="full"),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="running"),
        sa.Column("rollback_of", sa.String(length=32), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ota_batches_space_id", "ota_batches", ["space_id"], unique=False)

    op.add_column("ota_tasks", sa.Column("batch_id", sa.String(length=32), nullable=True))
    op.add_column(
        "ota_tasks",
        sa.Column("stage", sa.String(length=10), nullable=False, server_default="full"),
    )
    op.create_index("ix_ota_tasks_batch_id", "ota_tasks", ["batch_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ota_tasks_batch_id", table_name="ota_tasks")
    op.drop_column("ota_tasks", "stage")
    op.drop_column("ota_tasks", "batch_id")
    op.drop_index("ix_ota_batches_space_id", table_name="ota_batches")
    op.drop_table("ota_batches")
