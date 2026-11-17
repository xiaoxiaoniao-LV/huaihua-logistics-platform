"""交易加固：幂等、状态机 CAS、超时关闭、结算单、outbox。"""
from datetime import datetime, timedelta
from decimal import Decimal

from app.database import SessionLocal
from app.models import Order, OutboxEvent, Settlement
from app.services.outbox import dispatch_pending
from app.tasks import expire_orders_task


def _payload(res_id: int):
    return {
        "resource_id": res_id,
        "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.now() + timedelta(days=1)).isoformat(),
    }


def _session():
    return SessionLocal()


def test_idempotency_key_returns_same_order(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    headers = {**dem["headers"], "Idempotency-Key": "idem-order-1"}

    r1 = client.post("/api/v1/orders", headers=headers, json=_payload(res["id"]))
    r2 = client.post("/api/v1/orders", headers=headers, json=_payload(res["id"]))
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    db = _session()
    try:
        assert db.query(Order).filter(Order.resource_id == res["id"]).count() == 1
    finally:
        db.close()


def test_state_machine_rejects_skipping(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    admin = make_user(role="admin")
    res = make_resource(sup, status="available")
    order = client.post("/api/v1/orders", headers=dem["headers"],
                        json=_payload(res["id"])).json()

    # pending 不能直接 settled
    r = client.put(f"/api/v1/orders/{order['id']}/status", headers=admin["headers"],
                   params={"new_status": "settled"})
    assert r.status_code == 400


def test_finished_creates_settlement(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available", price=100)
    order = client.post("/api/v1/orders", headers=dem["headers"],
                        json=_payload(res["id"])).json()

    for st in ("confirmed", "ongoing", "finished"):
        assert client.put(f"/api/v1/orders/{order['id']}/status",
                          headers=sup["headers"],
                          params={"new_status": st}).status_code == 200

    db = _session()
    try:
        s = db.query(Settlement).filter(Settlement.order_id == order["id"]).one()
        assert s.status == "pending"
        assert s.amount == Decimal("100.00")
        assert s.commission == Decimal("10.00")
        assert s.payable_to_supplier == Decimal("90.00")
    finally:
        db.close()


def test_stale_order_expires_and_releases_resource(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/v1/orders", headers=dem["headers"],
                        json=_payload(res["id"])).json()

    db = _session()
    try:
        row = db.get(Order, order["id"])
        row.created_at = datetime.now() - timedelta(hours=49)
        db.commit()
        expired = expire_orders_task(db, hours=48)
        assert order["id"] in expired
        db.refresh(row)
        assert row.status == "expired"
    finally:
        db.close()

    assert client.get(f"/api/v1/resources/{res['id']}").json()["status"] == "available"


def test_order_created_emits_outbox_events(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/v1/orders", headers=dem["headers"],
                        json=_payload(res["id"])).json()

    db = _session()
    try:
        events = db.query(OutboxEvent).filter(OutboxEvent.status == "pending").all()
        types = {e.event_type for e in events}
        assert "order_created" in types
        assert "resource_updated" in types
        sent = dispatch_pending(db)
        assert sent >= 2
        assert db.query(OutboxEvent).filter(OutboxEvent.status == "pending").count() == 0
    finally:
        db.close()
    assert order["id"] > 0
