"""平台 v2：新增表约束与四端鉴权守卫。"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app import deps, security
from app.database import SessionLocal
from app.models import (
    DevicePoint,
    IdempotencyKey,
    Order,
    Space,
    Telemetry,
    TwinBinding,
    TwinNode,
)


def _session():
    return SessionLocal()


def _bearer(token: str):
    return SimpleNamespace(credentials=token)


def _token(uid: int, role: str, client: str) -> str:
    return security.create_access_token(str(uid), {"role": role}, client=client)


def test_space_tree_parent_child():
    db = _session()
    try:
        site = Space(code="PARK", name="怀化国际陆港", kind="site")
        db.add(site)
        db.commit()
        db.refresh(site)
        room = Space(code="PARK-A-01", name="A库1号冷库", kind="room", parent_id=site.id)
        db.add(room)
        db.commit()
        assert room.parent_id == site.id
        assert db.query(Space).filter_by(parent_id=site.id).count() == 1
    finally:
        db.close()


def test_device_point_unique_per_device():
    db = _session()
    try:
        db.add(DevicePoint(device_id=1, point_key="temp_in", name="库内温度"))
        db.commit()
        db.add(DevicePoint(device_id=1, point_key="temp_in", name="重复点位"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_telemetry_dedupes_same_point_and_ts():
    db = _session()
    try:
        ts = datetime(2026, 11, 9, 10, 0, 0)
        db.add(Telemetry(device_id=1, point_key="temp_in", ts=ts, value_num=-18.2))
        db.commit()
        # 断网补传重复上报：同一设备/点位/时间戳应被唯一约束拦截
        db.add(Telemetry(device_id=1, point_key="temp_in", ts=ts, value_num=-18.1))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_twin_binding_unique():
    db = _session()
    try:
        node = TwinNode(node_key="room-01", name="1号冷库")
        db.add(node)
        db.commit()
        db.refresh(node)
        db.add(TwinBinding(twin_node_id=node.id, device_id=1, point_key="temp_in"))
        db.commit()
        db.add(TwinBinding(twin_node_id=node.id, device_id=1, point_key="temp_in"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_idempotency_unique_scope_key():
    db = _session()
    try:
        db.add(IdempotencyKey(scope="order:create", idem_key="abc"))
        db.commit()
        db.add(IdempotencyKey(scope="order:create", idem_key="abc"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_order_payment_status_and_version_defaults():
    db = _session()
    try:
        o = Order(resource_id=1, supplier_id=1, demander_id=1)
        db.add(o)
        db.commit()
        db.refresh(o)
        assert o.payment_status == "unpaid"
        assert o.version == 0
        assert o.cancel_reason is None
    finally:
        db.close()


def test_supplier_guard_accepts_supplier_and_rejects_app(client, make_user):
    u = make_user(role="supplier")
    db = _session()
    try:
        assert deps.get_supplier_user(_bearer(_token(u["id"], "supplier", "supplier")), db).id == u["id"]
        with pytest.raises(HTTPException) as e:
            deps.get_supplier_user(_bearer(_token(u["id"], "supplier", "app")), db)
        assert e.value.status_code == 403
    finally:
        db.close()


def test_app_guard_accepts_app_and_rejects_supplier(client, make_user):
    u = make_user(role="demander")
    db = _session()
    try:
        assert deps.get_app_user(_bearer(_token(u["id"], "demander", "app")), db).id == u["id"]
        with pytest.raises(HTTPException) as e:
            deps.get_app_user(_bearer(_token(u["id"], "demander", "supplier")), db)
        assert e.value.status_code == 403
    finally:
        db.close()


def test_admin_guard_requires_admin_role(client, make_user):
    u = make_user(role="demander")
    db = _session()
    try:
        with pytest.raises(HTTPException) as e:
            deps.get_admin_user(_bearer(_token(u["id"], "demander", "admin")), db)
        assert e.value.status_code == 403
    finally:
        db.close()


def test_screen_viewer_allows_anonymous_and_screen(client, make_user):
    u = make_user(role="admin")
    db = _session()
    try:
        assert deps.get_screen_viewer(None, db) is None
        assert deps.get_screen_viewer(_bearer(_token(u["id"], "admin", "screen")), db).id == u["id"]
        with pytest.raises(HTTPException) as e:
            deps.get_screen_viewer(_bearer(_token(u["id"], "admin", "app")), db)
        assert e.value.status_code == 403
    finally:
        db.close()
