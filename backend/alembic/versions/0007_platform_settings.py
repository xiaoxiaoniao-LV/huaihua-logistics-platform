"""platform settings: runtime config (matching weights)

Revision ID: 0007_platform_settings
Revises: 0006_ota_rollout
Create Date: 2026-11-19

说明：
- 新增 platform_settings 键值表，存运行时可改的 JSON 配置；
- 首个使用方是撮合权重 matching_weights，缺省时按内置默认值。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_platform_settings"
down_revision: Union[str, None] = "0006_ota_rollout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
