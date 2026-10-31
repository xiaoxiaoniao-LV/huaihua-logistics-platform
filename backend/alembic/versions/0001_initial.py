"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- users ----------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="demander"),
        sa.Column("company_name", sa.String(length=100), nullable=True),
        sa.Column("contact", sa.String(length=50), nullable=True),
        sa.Column("credit_score", sa.Integer(), nullable=True, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # ---------- resources ----------
    op.create_table(
        "resources",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("available_start", sa.DateTime(), nullable=True),
        sa.Column("available_end", sa.DateTime(), nullable=True),
        sa.Column("price", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("price_unit", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resources_user_id", "resources", ["user_id"], unique=False)

    # ---------- orders ----------
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("resource_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("demander_id", sa.BigInteger(), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("total_price", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("commission_rate", sa.DECIMAL(precision=5, scale=4), nullable=False, server_default="0.1000"),
        sa.Column("commission", sa.DECIMAL(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_resource_id", "orders", ["resource_id"], unique=False)

    # ---------- reviews ----------
    op.create_table(
        "reviews",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("from_user_id", sa.BigInteger(), nullable=False),
        sa.Column("to_user_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True, server_default="5"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reviews_order_id", "reviews", ["order_id"], unique=False)

    # ---------- iot_devices ----------
    op.create_table(
        "iot_devices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("resource_id", sa.BigInteger(), nullable=False),
        sa.Column("device_code", sa.String(length=50), nullable=False),
        sa.Column("device_type", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="offline"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_iot_devices_resource_id", "iot_devices", ["resource_id"], unique=False)
    op.create_index("ix_iot_devices_device_code", "iot_devices", ["device_code"], unique=True)

    # ---------- iot_data ----------
    op.create_table(
        "iot_data",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_iot_data_device_id", "iot_data", ["device_id"], unique=False)
    op.create_index("ix_iot_data_recorded_at", "iot_data", ["recorded_at"], unique=False)

    # ---------- alerts ----------
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=True),
        sa.Column("level", sa.String(length=20), nullable=True, server_default="info"),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_device_id", "alerts", ["device_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alerts_device_id", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_iot_data_recorded_at", table_name="iot_data")
    op.drop_index("ix_iot_data_device_id", table_name="iot_data")
    op.drop_table("iot_data")

    op.drop_index("ix_iot_devices_device_code", table_name="iot_devices")
    op.drop_index("ix_iot_devices_resource_id", table_name="iot_devices")
    op.drop_table("iot_devices")

    op.drop_index("ix_reviews_order_id", table_name="reviews")
    op.drop_table("reviews")

    op.drop_index("ix_orders_resource_id", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_resources_user_id", table_name="resources")
    op.drop_table("resources")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
