"""资源与订单核心规则。"""
from datetime import datetime, timedelta


def _order_payload(resource_id, start, days=1):
    return {
        "resource_id": resource_id,
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(days=days)).isoformat(),
    }


def test_new_resource_is_pending(client, make_user, make_resource):
    sup = make_user(role="supplier")
    res = make_resource(sup)
    assert res["status"] == "pending"


def test_only_owner_or_admin_can_modify(client, make_user, make_resource):
    sup = make_user(role="supplier")
    other = make_user(role="supplier")
    admin = make_user(role="admin")
    res = make_resource(sup)

    assert client.put(f"/api/resources/{res['id']}", headers=other["headers"],
                      json={"name": "改名"}).status_code == 403
    assert client.delete(f"/api/resources/{res['id']}", headers=other["headers"]).status_code == 403
    assert client.put(f"/api/resources/{res['id']}", headers=admin["headers"],
                      json={"name": "管理员改名"}).status_code == 200


def test_order_requires_available_resource(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup)  # pending
    r = client.post("/api/orders", headers=dem["headers"],
                    json=_order_payload(res["id"], datetime.now() + timedelta(hours=1)))
    assert r.status_code == 400


def test_create_order_marks_resource_booked(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    start = datetime.now() + timedelta(hours=1)

    r = client.post("/api/orders", headers=dem["headers"], json=_order_payload(res["id"], start))
    assert r.status_code == 201
    order = r.json()
    assert order["status"] == "pending"
    assert float(order["total_price"]) == 100.0
    assert float(order["commission_rate"]) == 0.10

    assert client.get(f"/api/resources/{res['id']}").json()["status"] == "booked"


def test_order_time_overlap_rejected(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    start = datetime.now() + timedelta(hours=1)

    assert client.post("/api/orders", headers=dem["headers"],
                       json=_order_payload(res["id"], start)).status_code == 201

    # 所有者把资源改回可预约（模拟释放），再下重叠时段
    client.put(f"/api/resources/{res['id']}", headers=sup["headers"], json={"status": "available"})
    r = client.post("/api/orders", headers=dem["headers"],
                    json=_order_payload(res["id"], start + timedelta(hours=2)))
    assert r.status_code == 409


def test_order_outside_available_window_rejected(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    future = datetime.now() + timedelta(days=30)
    res = make_resource(
        sup, status="available",
        available_start=(future).isoformat(),
        available_end=(future + timedelta(days=3)).isoformat(),
    )
    r = client.post("/api/orders", headers=dem["headers"],
                    json=_order_payload(res["id"], datetime.now() + timedelta(hours=1)))
    assert r.status_code == 400


def test_order_invalid_time_range(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    start = datetime.now() + timedelta(days=1)
    r = client.post("/api/orders", headers=dem["headers"], json={
        "resource_id": res["id"],
        "start_time": start.isoformat(),
        "end_time": (start - timedelta(hours=1)).isoformat(),
    })
    assert r.status_code == 422


def test_order_lifecycle_and_commission(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    admin = make_user(role="admin")
    res = make_resource(sup, status="available")

    order = client.post("/api/orders", headers=dem["headers"],
                        json=_order_payload(res["id"], datetime.now() + timedelta(hours=1),
                                            days=2)).json()
    assert float(order["total_price"]) == 200.0

    for status in ("confirmed", "ongoing", "finished"):
        r = client.put(f"/api/orders/{order['id']}/status",
                       headers=admin["headers"], params={"new_status": status})
        assert r.status_code == 200, r.text

    final = client.get("/api/orders", headers=dem["headers"]).json()[0]
    assert final["status"] == "finished"
    assert float(final["commission"]) == 20.0  # 200 * 0.10
    # 完成后资源释放回可预约
    assert client.get(f"/api/resources/{res['id']}").json()["status"] == "available"


def test_cancel_releases_resource(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/orders", headers=dem["headers"],
                        json=_order_payload(res["id"], datetime.now() + timedelta(hours=1))).json()

    r = client.put(f"/api/orders/{order['id']}/status", headers=dem["headers"],
                   params={"new_status": "cancelled"})
    assert r.status_code == 200
    assert r.json()["commission"] is None
    assert client.get(f"/api/resources/{res['id']}").json()["status"] == "available"


def test_non_participant_cannot_change_status(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    outsider = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/orders", headers=dem["headers"],
                        json=_order_payload(res["id"], datetime.now() + timedelta(hours=1))).json()

    r = client.put(f"/api/orders/{order['id']}/status", headers=outsider["headers"],
                   params={"new_status": "confirmed"})
    assert r.status_code == 403


def test_invalid_status_rejected(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/orders", headers=dem["headers"],
                        json=_order_payload(res["id"], datetime.now() + timedelta(hours=1))).json()
    r = client.put(f"/api/orders/{order['id']}/status", headers=dem["headers"],
                   params={"new_status": "unknown"})
    assert r.status_code == 400


# ---------------- 资源审核流程 ----------------

def test_owner_cannot_self_approve_pending(client, make_user, make_resource):
    sup = make_user(role="supplier")
    res = make_resource(sup)
    r = client.put(f"/api/resources/{res['id']}", headers=sup["headers"],
                   json={"status": "available"})
    assert r.status_code == 403


def test_admin_approve_then_owner_can_toggle(client, make_user, make_resource):
    sup = make_user(role="supplier")
    admin = make_user(role="admin")
    res = make_resource(sup)

    r = client.post(f"/api/resources/{res['id']}/review", headers=admin["headers"],
                    json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "available"

    # 审核通过后属主可自由上下架
    assert client.put(f"/api/resources/{res['id']}", headers=sup["headers"],
                      json={"status": "offline"}).status_code == 200
    assert client.put(f"/api/resources/{res['id']}", headers=sup["headers"],
                      json={"status": "available"}).status_code == 200


def test_admin_reject_sets_offline(client, make_user, make_resource):
    sup = make_user(role="supplier")
    admin = make_user(role="admin")
    res = make_resource(sup)
    r = client.post(f"/api/resources/{res['id']}/review", headers=admin["headers"],
                    json={"approve": False, "reason": "资料不全"})
    assert r.status_code == 200 and r.json()["status"] == "offline"


def test_review_requires_admin(client, make_user, make_resource):
    sup = make_user(role="supplier")
    res = make_resource(sup)
    r = client.post(f"/api/resources/{res['id']}/review", headers=sup["headers"],
                    json={"approve": True})
    assert r.status_code == 403


def test_review_only_for_pending(client, make_user, make_resource):
    sup = make_user(role="supplier")
    admin = make_user(role="admin")
    res = make_resource(sup, status="available")
    r = client.post(f"/api/resources/{res['id']}/review", headers=admin["headers"],
                    json={"approve": True})
    assert r.status_code == 400


# ---------------- 列表分页 ----------------

def test_resources_pagination(client, make_user, make_resource):
    sup = make_user(role="supplier")
    for i in range(3):
        make_resource(sup, status="available", name=f"分页资源{i}")

    r1 = client.get("/api/resources", params={"page": 1, "page_size": 2})
    assert len(r1.json()) == 2
    assert r1.headers["x-total-count"] == "3"

    r2 = client.get("/api/resources", params={"page": 2, "page_size": 2})
    assert len(r2.json()) == 1
    assert r2.headers["x-total-count"] == "3"
    # 两页内容不重复
    assert not ({x["id"] for x in r1.json()} & {x["id"] for x in r2.json()})


def test_orders_pagination(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    for _ in range(2):
        res = make_resource(sup, status="available")
        r = client.post("/api/orders", headers=dem["headers"],
                        json=_order_payload(res["id"], datetime.now() + timedelta(hours=1)))
        assert r.status_code == 201

    r1 = client.get("/api/orders", headers=dem["headers"], params={"page": 1, "page_size": 1})
    assert len(r1.json()) == 1 and r1.headers["x-total-count"] == "2"

    r2 = client.get("/api/orders", headers=dem["headers"], params={"page": 2, "page_size": 1})
    assert len(r2.json()) == 1
    assert r2.json()[0]["id"] != r1.json()[0]["id"]
