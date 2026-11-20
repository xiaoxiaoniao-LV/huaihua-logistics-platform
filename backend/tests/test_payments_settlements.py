"""支付沙箱旁路、结算单与对账。"""
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import PaymentEvent


def _payload(res_id: int, price_days: int = 1):
    return {
        "resource_id": res_id,
        "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.now() + timedelta(hours=1, days=price_days)).isoformat(),
    }


def _session():
    return SessionLocal()


def _make_order(client, make_user, make_resource, price=None):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available", **({"price": price} if price else {}))
    order = client.post("/api/v1/orders", headers=dem["headers"],
                        json=_payload(res["id"])).json()
    return sup, dem, res, order


def test_payment_intent_and_mock_checkout(client, make_user, make_resource):
    sup, dem, res, order = _make_order(client, make_user, make_resource, price=100)

    r = client.post(f"/api/v1/payments/{order['id']}/intent", headers=dem["headers"])
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "alipay_sandbox"
    assert data["trade_no"].startswith("SBX")

    r = client.get("/api/v1/payments/mock-checkout",
                   params={"order_id": order["id"], "trade_no": data["trade_no"]},
                   headers=dem["headers"])
    assert r.status_code == 200
    assert r.json()["payment_status"] == "paid"

    detail = client.get(f"/api/v1/orders?mine=demander", headers=dem["headers"]).json()
    assert detail[0]["payment_status"] == "paid"


def test_mock_checkout_rejects_unauthorized(client, make_user, make_resource):
    """无 token 或非订单相关方不能触发模拟支付，防止越权把他人订单置为已付。"""
    sup, dem, res, order = _make_order(client, make_user, make_resource, price=100)

    intent = client.post(f"/api/v1/payments/{order['id']}/intent", headers=dem["headers"]).json()

    # 无鉴权 → 401
    r = client.get("/api/v1/payments/mock-checkout",
                   params={"order_id": order["id"], "trade_no": intent["trade_no"]})
    assert r.status_code == 401

    # 无关第三方（另一个 demander）→ 403
    other = make_user()
    r = client.get("/api/v1/payments/mock-checkout",
                   params={"order_id": order["id"], "trade_no": intent["trade_no"]},
                   headers=other["headers"])
    assert r.status_code == 403

    # 交易号与订单不匹配 → 400
    r = client.get("/api/v1/payments/mock-checkout",
                   params={"order_id": order["id"], "trade_no": f"SBX{order['id'] + 1}-123"},
                   headers=dem["headers"])
    assert r.status_code == 400


def test_alipay_notify_is_idempotent(client, make_user, make_resource):
    sup, dem, res, order = _make_order(client, make_user, make_resource, price=100)
    notify = {
        "order_id": order["id"],
        "trade_no": f"SBX{order['id']}-1700000000000",
        "trade_status": "TRADE_SUCCESS",
        "total_amount": "100.00",
    }
    r1 = client.post("/api/v1/payments/notify/alipay", json=notify)
    r2 = client.post("/api/v1/payments/notify/alipay", json=notify)
    assert r1.json()["code"] == "10000"
    # 重复通知不重复记账
    assert r2.json()["code"] == "40004"

    db = _session()
    try:
        assert db.query(PaymentEvent).filter(PaymentEvent.order_id == order["id"]).count() == 1
    finally:
        db.close()


def test_settlement_lifecycle_and_reconciliation(client, make_user, make_resource):
    sup, dem, res, order = _make_order(client, make_user, make_resource, price=100)
    admin = make_user(role="admin")

    for st in ("confirmed", "ongoing", "finished"):
        client.put(f"/api/v1/orders/{order['id']}/status", headers=sup["headers"],
                   params={"new_status": st})

    items = client.get("/api/v1/settlements", headers=sup["headers"]).json()
    assert len(items) == 1
    sid = items[0]["id"]
    assert items[0]["status"] == "pending"

    # 需求方看不到与自己无关的结算单
    assert client.get("/api/v1/settlements", headers=dem["headers"]).json() == []

    # 非管理员不能改结算状态
    assert client.put(f"/api/v1/settlements/{sid}/status", headers=sup["headers"],
                      params={"new_status": "confirmed"}).status_code == 403

    r = client.put(f"/api/v1/settlements/{sid}/status", headers=admin["headers"],
                   params={"new_status": "confirmed"})
    assert r.status_code == 200
    r = client.put(f"/api/v1/settlements/{sid}/status", headers=admin["headers"],
                   params={"new_status": "paid"})
    assert r.status_code == 200
    assert r.json()["settled_at"] is not None

    # 已打款不可回退
    assert client.put(f"/api/v1/settlements/{sid}/status", headers=admin["headers"],
                      params={"new_status": "void"}).status_code == 400

    rec = client.get("/api/v1/settlements/reconciliation", headers=admin["headers"])
    assert rec.status_code == 200
    assert rec.json()["orders"] >= 1
    assert rec.json()["gmv"] >= 100


def _finish_order(client, headers, order_id: int) -> None:
    for st in ("confirmed", "ongoing", "finished"):
        r = client.put(f"/api/v1/orders/{order_id}/status", headers=headers,
                       params={"new_status": st})
        assert r.status_code == 200, r.text


def test_settlement_split_and_invoice_pdf(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    admin = make_user(role="admin")
    outsider = make_user(role="supplier")

    for _ in range(2):
        res = make_resource(sup, status="available", price="100.00")
        order = client.post("/api/v1/orders", headers=dem["headers"],
                            json=_payload(res["id"])).json()
        _finish_order(client, sup["headers"], order["id"])

    items = client.get("/api/v1/settlements", headers=sup["headers"]).json()
    assert len(items) == 2
    sid = items[0]["id"]
    for st in ("confirmed", "paid"):
        assert client.put(f"/api/v1/settlements/{sid}/status", headers=admin["headers"],
                          params={"new_status": st}).status_code == 200

    # 租户分账：同一供给方两笔，已付/待付各 90
    split = client.get("/api/v1/settlements/split", headers=admin["headers"])
    assert split.status_code == 200
    data = split.json()
    assert data["suppliers"] == 1
    row = data["items"][0]
    assert row["supplier_id"] == sup["id"]
    assert row["settlements"] == 2
    assert row["amount"] == 200.0
    assert row["commission"] == 20.0
    assert row["payable"] == 180.0
    assert row["paid"] == 90.0
    assert row["unpaid"] == 90.0
    assert data["total"]["settlements"] == 2
    assert data["total"]["payable"] == 180.0
    # 非管理员不能看全平台分账
    assert client.get("/api/v1/settlements/split", headers=sup["headers"]).status_code == 403

    # 发票 PDF：供给方本人与管理可下载，他人 403
    inv = client.get(f"/api/v1/settlements/{sid}/invoice.pdf", headers=sup["headers"])
    assert inv.status_code == 200
    assert inv.content.startswith(b"%PDF")
    assert inv.headers["content-type"].startswith("application/pdf")
    assert "attachment" in inv.headers["content-disposition"]
    assert client.get(f"/api/v1/settlements/{sid}/invoice.pdf",
                      headers=admin["headers"]).status_code == 200
    assert client.get(f"/api/v1/settlements/{sid}/invoice.pdf",
                      headers=outsider["headers"]).status_code == 403

    # 作废的结算单不再开票，也不再计入分账
    other_sid = next(i["id"] for i in items if i["id"] != sid)
    assert client.put(f"/api/v1/settlements/{other_sid}/status", headers=admin["headers"],
                      params={"new_status": "void"}).status_code == 200
    assert client.get(f"/api/v1/settlements/{other_sid}/invoice.pdf",
                      headers=admin["headers"]).status_code == 400
    split = client.get("/api/v1/settlements/split", headers=admin["headers"]).json()
    assert split["total"]["settlements"] == 1
    assert split["total"]["payable"] == 90.0
