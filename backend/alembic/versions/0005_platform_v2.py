"""platform v2: spaces / twin / telemetry / outbox / idempotency / trade

Revision ID: 0005_platform_v2
Revises: 0004_ota_tasks
Create Date: 2026-11-09

说明：
- 订单新增 payment_status 与 version，实现「履约状态与支付状态正交」+ 乐观锁 CAS；
- 遥测改为窄表（一行一个点位），并唯一约束 (device_id, point_key, ts) 支撑断网补传去重；
- outbox / idempotency 为交易加固提供事务外盒与幂等能力。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_platform_v2"
down_revision: Union[str, None] = "0004_ota_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _now() -> sa.text:
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    # ---------- 用户：多角色 ----------
    op.add_column("users", sa.Column("roles", sa.JSON(), nullable=True))

    # ---------- 订单：支付状态 + 乐观锁 ----------
    op.add_column(
        "orders",
        sa.Column("payment_status", sa.String(length=20), nullable=False,
                  server_default="unpaid"),
    )
    op.add_column("orders", sa.Column("cancel_reason", sa.String(length=255), nullable=True))
    op.add_column(
        "orders",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("updated_at", sa.DateTime(), nullable=True,
                  server_default=_now()),
    )

    # ---------- 设备：空间归属 + 数据质量 ----------
    op.add_column("iot_devices", sa.Column("name", sa.String(length=100), nullable=True))
    op.add_column("iot_devices", sa.Column("space_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "iot_devices",
        sa.Column("quality", sa.String(length=10), nullable=False,
                  server_default="unknown"),
    )
    op.add_column("iot_devices", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.create_index("ix_iot_devices_space_id", "iot_devices", ["space_id"], unique=False)

    # ---------- 空间树 ----------
    op.create_table(
        "spaces",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="room"),
        sa.Column("capacity", sa.JSON(), nullable=True),
        sa.Column("geo", sa.JSON(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_spaces_code"),
    )
    op.create_index("ix_spaces_code", "spaces", ["code"], unique=False)

    # ---------- 点位字典 ----------
    op.create_table(
        "device_points",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("point_key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("data_type", sa.String(length=10), nullable=False, server_default="number"),
        sa.Column("precision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("writable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "point_key", name="uq_device_point"),
    )
    op.create_index("ix_device_points_device_id", "device_points", ["device_id"], unique=False)

    # ---------- 孪生节点与绑定 ----------
    op.create_table(
        "twin_nodes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("node_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("node_type", sa.String(length=20), nullable=False, server_default="room"),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("space_id", sa.BigInteger(), nullable=True),
        sa.Column("model_ref", sa.String(length=200), nullable=True),
        sa.Column("transform", sa.JSON(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_key", name="uq_twin_nodes_key"),
    )
    op.create_index("ix_twin_nodes_key", "twin_nodes", ["node_key"], unique=False)
    op.create_index("ix_twin_nodes_parent_id", "twin_nodes", ["parent_id"], unique=False)
    op.create_index("ix_twin_nodes_space_id", "twin_nodes", ["space_id"], unique=False)

    op.create_table(
        "twin_bindings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("twin_node_id", sa.BigInteger(), nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("point_key", sa.String(length=50), nullable=False),
        sa.Column("binding_type", sa.String(length=20), nullable=False,
                  server_default="telemetry"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("twin_node_id", "device_id", "point_key", name="uq_twin_binding"),
    )
    op.create_index("ix_twin_bindings_node", "twin_bindings", ["twin_node_id"], unique=False)
    op.create_index("ix_twin_bindings_device", "twin_bindings", ["device_id"], unique=False)

    # ---------- 遥测窄表 ----------
    op.create_table(
        "telemetry",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("point_key", sa.String(length=50), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("value_num", sa.Float(), nullable=True),
        sa.Column("value_text", sa.String(length=64), nullable=True),
        sa.Column("quality", sa.String(length=10), nullable=False, server_default="good"),
        sa.Column("seq", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "point_key", "ts", name="uq_telemetry_point_ts"),
    )
    op.create_index("ix_telemetry_device_ts", "telemetry", ["device_id", "ts"], unique=False)

    # ---------- 设备事件 ----------
    op.create_table(
        "device_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="info"),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("ts", sa.DateTime(), nullable=True, server_default=_now()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_events_device_id", "device_events", ["device_id"], unique=False)
    op.create_index("ix_device_events_ts", "device_events", ["ts"], unique=False)

    # ---------- outbox ----------
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("aggregate_type", sa.String(length=40), nullable=False),
        sa.Column("aggregate_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"], unique=False)

    # ---------- 幂等键 ----------
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("idem_key", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "idem_key", name="uq_idem_scope_key"),
    )

    # ---------- 支付事件 ----------
    op.create_table(
        "payment_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_txn_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_txn_id", name="uq_payment_provider_txn"),
    )
    op.create_index("ix_payment_events_order_id", "payment_events", ["order_id"], unique=False)

    # ---------- 结算单 ----------
    op.create_table(
        "settlements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.DECIMAL(12, 2), nullable=False),
        sa.Column("commission_rate", sa.DECIMAL(5, 4), nullable=False, server_default="0.1000"),
        sa.Column("commission", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
        sa.Column("payable_to_supplier", sa.DECIMAL(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=_now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_settlement_order"),
    )
    op.create_index("ix_settlements_supplier_id", "settlements", ["supplier_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_settlements_supplier_id", table_name="settlements")
    op.drop_table("settlements")
    op.drop_index("ix_payment_events_order_id", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_outbox_events_status", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_device_events_ts", table_name="device_events")
    op.drop_index("ix_device_events_device_id", table_name="device_events")
    op.drop_table("device_events")
    op.drop_index("ix_telemetry_device_ts", table_name="telemetry")
    op.drop_table("telemetry")
    op.drop_index("ix_twin_bindings_device", table_name="twin_bindings")
    op.drop_index("ix_twin_bindings_node", table_name="twin_bindings")
    op.drop_table("twin_bindings")
    op.drop_index("ix_twin_nodes_space_id", table_name="twin_nodes")
    op.drop_index("ix_twin_nodes_parent_id", table_name="twin_nodes")
    op.drop_index("ix_twin_nodes_key", table_name="twin_nodes")
    op.drop_table("twin_nodes")
    op.drop_index("ix_device_points_device_id", table_name="device_points")
    op.drop_table("device_points")
    op.drop_index("ix_spaces_code", table_name="spaces")
    op.drop_table("spaces")
    op.drop_index("ix_iot_devices_space_id", table_name="iot_devices")
    op.drop_column("iot_devices", "last_seen_at")
    op.drop_column("iot_devices", "quality")
    op.drop_column("iot_devices", "space_id")
    op.drop_column("iot_devices", "name")
    op.drop_column("orders", "updated_at")
    op.drop_column("orders", "version")
    op.drop_column("orders", "cancel_reason")
    op.drop_column("orders", "payment_status")
    op.drop_column("users", "roles")
