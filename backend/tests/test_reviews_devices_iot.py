"""评价、设备与 IoT 接入。"""
from datetime import datetime, timedelta

DEVICE_TOKEN = {"X-Device-Token": "test-device-token"}


def _make_finished_order(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/orders", headers=dem["headers"], json={
        "resource_id": res["id"],
        "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.now() + timedelta(days=1)).isoformat(),
    }).json()
    client.put(f"/api/orders/{order['id']}/status", headers=sup["headers"],
               params={"new_status": "finished"})
    return sup, dem, res, order


# ---------------- 评价 ----------------

def test_review_requires_finished_order(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/orders", headers=dem["headers"], json={
        "resource_id": res["id"],
        "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.now() + timedelta(days=1)).isoformat(),
    }).json()

    r = client.post("/api/reviews", headers=dem["headers"],
                    json={"order_id": order["id"], "rating": 5})
    assert r.status_code == 400


def test_review_updates_credit_score(client, make_user, make_resource):
    sup, dem, _res, order = _make_finished_order(client, make_user, make_resource)

    # 需求方给供给方 5 星 → 供给方 100 分
    r = client.post("/api/reviews", headers=dem["headers"],
                    json={"order_id": order["id"], "rating": 5, "content": "很好"})
    assert r.status_code == 201
    assert client.get(f"/api/reviews/user/{sup['id']}").json()["credit_score"] == 100

    # 供给方给需求方 4 星 → 60 + 40*3/4 = 90
    r = client.post("/api/reviews", headers=sup["headers"],
                    json={"order_id": order["id"], "rating": 4})
    assert r.status_code == 201
    summary = client.get(f"/api/reviews/user/{dem['id']}").json()
    assert summary["credit_score"] == 90
    assert summary["average"] == 4.0
    assert summary["count"] == 1


def test_review_duplicate_rejected(client, make_user, make_resource):
    _sup, dem, _res, order = _make_finished_order(client, make_user, make_resource)
    payload = {"order_id": order["id"], "rating": 5}
    assert client.post("/api/reviews", headers=dem["headers"], json=payload).status_code == 201
    assert client.post("/api/reviews", headers=dem["headers"], json=payload).status_code == 400


def test_review_by_outsider_rejected(client, make_user, make_resource):
    _sup, _dem, _res, order = _make_finished_order(client, make_user, make_resource)
    outsider = make_user()
    r = client.post("/api/reviews", headers=outsider["headers"],
                    json={"order_id": order["id"], "rating": 1})
    assert r.status_code == 403


def test_order_reviews_visible_to_participant_only(client, make_user, make_resource):
    _sup, dem, _res, order = _make_finished_order(client, make_user, make_resource)
    client.post("/api/reviews", headers=dem["headers"], json={"order_id": order["id"], "rating": 5})

    r = client.get(f"/api/reviews/order/{order['id']}", headers=dem["headers"])
    assert r.status_code == 200 and len(r.json()) == 1

    outsider = make_user()
    assert client.get(f"/api/reviews/order/{order['id']}",
                      headers=outsider["headers"]).status_code == 403


# ---------------- 设备 ----------------

def test_register_bind_device_and_query(client, make_user, make_resource):
    sup = make_user(role="supplier")
    res = make_resource(sup, status="available")

    r = client.post("/api/devices", headers=sup["headers"], json={
        "device_code": "CW-T1", "device_type": "esp32", "resource_id": res["id"],
    })
    assert r.status_code == 201
    dev = r.json()
    assert dev["resource_id"] == res["id"]
    assert dev["resource_name"] == res["name"]

    lst = client.get("/api/devices", params={"resource_id": res["id"]}).json()
    assert len(lst) == 1 and lst[0]["device_code"] == "CW-T1"
    assert client.get(f"/api/devices/{dev['id']}/telemetry").json()["count"] == 0


def test_auto_bind_unbound_devices(client, make_user, make_resource):
    sup = make_user(role="supplier")
    admin = make_user(role="admin")
    res1 = make_resource(sup, status="available")
    res2 = make_resource(sup, status="available")

    client.post("/api/devices", headers=sup["headers"], json={"device_code": "A1"})
    client.post("/api/devices", headers=sup["headers"], json={"device_code": "A2"})

    r = client.post("/api/devices/auto-bind", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["bound"] == 2

    bound = {d["device_code"]: d["resource_id"] for d in client.get("/api/devices").json()}
    assert set(bound.values()) == {res1["id"], res2["id"]}


# ---------------- IoT 上报与告警 ----------------

def test_iot_report_requires_device_token(client):
    payload = {"device_code": "CW-T1", "temperature": -18.0}
    assert client.post("/api/iot/data", json=payload).status_code == 401
    assert client.post("/api/iot/data", json=payload,
                       headers={"X-Device-Token": "wrong"}).status_code == 401
    assert client.post("/api/iot/data", json=payload, headers=DEVICE_TOKEN).status_code == 201


def test_iot_data_returns_resource_id(client, make_user, make_resource):
    sup = make_user(role="supplier")
    res = make_resource(sup, status="available")
    client.post("/api/devices", headers=sup["headers"],
                json={"device_code": "CW-T1", "resource_id": res["id"]})

    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "CW-T1", "temperature": -18.5, "humidity": 60.0})

    data = client.get("/api/iot/data", params={"limit": 5}).json()["data"]
    assert len(data) == 1
    assert data[0]["resource_id"] == res["id"]
    assert data[0]["device_code"] == "CW-T1"


def test_alert_created_on_abnormal_temperature(client, make_user, make_resource):
    sup = make_user(role="supplier")
    res = make_resource(sup, status="available")
    client.post("/api/devices", headers=sup["headers"],
                json={"device_code": "CW-T1", "resource_id": res["id"]})

    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "CW-T1", "temperature": 10.0, "humidity": 50.0})

    alerts = client.get("/api/iot/alerts", params={"status": "active"}).json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["level"] == "critical"
    assert alerts[0]["type"] == "temperature_high"
    assert alerts[0]["device_code"] == "CW-T1"
    assert alerts[0]["resource_id"] == res["id"]


def test_resolve_alert(client, make_user, make_resource):
    sup = make_user(role="supplier")
    res = make_resource(sup, status="available")
    client.post("/api/devices", headers=sup["headers"],
                json={"device_code": "CW-T1", "resource_id": res["id"]})
    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "CW-T1", "temperature": 10.0})

    alert_id = client.get("/api/iot/alerts", params={"status": "active"}).json()["alerts"][0]["id"]

    # 未登录不能处理告警
    assert client.post(f"/api/iot/alerts/{alert_id}/resolve").status_code == 401

    r = client.post(f"/api/iot/alerts/{alert_id}/resolve", headers=sup["headers"])
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert client.get("/api/iot/alerts", params={"status": "active"}).json()["count"] == 0

    resolved = client.get("/api/iot/alerts", params={"status": "resolved"}).json()["alerts"]
    assert len(resolved) == 1 and resolved[0]["status"] == "resolved"

    # 重复处理幂等
    assert client.post(f"/api/iot/alerts/{alert_id}/resolve",
                       headers=sup["headers"]).status_code == 200


def test_resolve_missing_alert(client, make_user):
    user = make_user()
    assert client.post("/api/iot/alerts/999999/resolve",
                       headers=user["headers"]).status_code == 404


# ---------------- 告警阈值规则 ----------------

def _device_with_resource(client, make_user, make_resource, code="RULE-1"):
    sup = make_user(role="supplier")
    res = make_resource(sup, status="available")
    client.post("/api/devices", headers=sup["headers"],
                json={"device_code": code, "resource_id": res["id"]})
    return sup, res


def test_alert_rules_default_and_global(client, make_user, make_resource):
    admin = make_user(role="admin")
    sup, res = _device_with_resource(client, make_user, make_resource)

    # 未配置任何规则时，接口返回一条全局默认（id=0）
    rules = client.get("/api/iot/rules").json()
    assert len(rules) == 1
    assert rules[0]["resource_id"] == 0 and rules[0]["id"] == 0
    assert rules[0]["temp_min"] == -30 and rules[0]["temp_max"] == -5
    assert rules[0]["humidity_max"] == 90

    # 全局上限放宽到 10℃ 后，0℃ 不再告警
    r = client.put("/api/iot/rules/0", headers=admin["headers"], json={"temp_max": 10})
    assert r.status_code == 200 and r.json()["temp_max"] == 10

    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "RULE-1", "temperature": 0.0})
    assert client.get("/api/iot/alerts", params={"status": "active"}).json()["count"] == 0

    # 资源级规则优先于全局：把该资源上限收紧到 -20℃
    r = client.put(f"/api/iot/rules/{res['id']}", headers=admin["headers"],
                   json={"temp_max": -20})
    assert r.status_code == 200 and r.json()["resource_name"] == res["name"]

    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "RULE-1", "temperature": -18.0})
    alerts = client.get("/api/iot/alerts", params={"status": "active"}).json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["type"] == "temperature_high"

    # 删除资源级规则后回到全局规则
    assert client.delete(f"/api/iot/rules/{res['id']}",
                         headers=admin["headers"]).status_code == 204
    assert len(client.get("/api/iot/rules").json()) == 1


def test_alert_rule_can_disable_and_validates(client, make_user, make_resource):
    admin = make_user(role="admin")
    _sup, res = _device_with_resource(client, make_user, make_resource, code="RULE-2")

    r = client.put(f"/api/iot/rules/{res['id']}", headers=admin["headers"],
                   json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False

    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "RULE-2", "temperature": -60.0})
    assert client.get("/api/iot/alerts", params={"status": "active"}).json()["count"] == 0

    # 下限不小于上限 → 参数校验失败
    r = client.put(f"/api/iot/rules/{res['id']}", headers=admin["headers"],
                   json={"temp_min": 10, "temp_max": 5})
    assert r.status_code == 422

    # 只改下限、与已存上限冲突时由路由层拦截
    r = client.put(f"/api/iot/rules/{res['id']}", headers=admin["headers"],
                   json={"temp_min": 10})
    assert r.status_code == 400

    # 非管理员无权改规则
    sup = make_user(role="supplier")
    assert client.put("/api/iot/rules/0", headers=sup["headers"],
                      json={"temp_max": 1}).status_code == 403


def test_device_manage_permissions(client, make_user, make_resource):
    owner = make_user(role="supplier")
    other = make_user(role="supplier")
    admin = make_user(role="admin")
    res = make_resource(owner, status="available")
    dev = client.post("/api/devices", headers=owner["headers"],
                      json={"device_code": "PERM-1", "resource_id": res["id"]}).json()

    # 他人不能改/删
    assert client.put(f"/api/devices/{dev['id']}", headers=other["headers"],
                      json={"device_type": "dht22"}).status_code == 403
    assert client.delete(f"/api/devices/{dev['id']}", headers=other["headers"]).status_code == 403

    # 属主可改，管理员可删
    assert client.put(f"/api/devices/{dev['id']}", headers=owner["headers"],
                      json={"device_type": "dht22"}).status_code == 200
    assert client.delete(f"/api/devices/{dev['id']}",
                         headers=admin["headers"]).status_code == 204

    # 普通用户不能批量绑定
    assert client.post("/api/devices/auto-bind", headers=owner["headers"]).status_code == 403


# ---------------- 设备离线检测 ----------------

def test_mark_offline_devices(client, make_user, make_resource):
    from app.database import SessionLocal
    from app.models import IoTData, IoTDevice
    from app.tasks import mark_offline_devices

    sup = make_user(role="supplier")
    res = make_resource(sup, status="available")
    client.post("/api/devices", headers=sup["headers"],
                json={"device_code": "LIVE", "resource_id": res["id"]})
    client.post("/api/devices", headers=sup["headers"],
                json={"device_code": "STALE", "resource_id": res["id"]})

    # LIVE 刚刚上报过一条数据
    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "LIVE", "temperature": -18.0})

    db = SessionLocal()
    try:
        # 两台都置为在线
        db.query(IoTDevice).filter(
            IoTDevice.device_code.in_(["LIVE", "STALE"])
        ).update({"status": "online"}, synchronize_session=False)

        stale = db.query(IoTDevice).filter(IoTDevice.device_code == "STALE").one()
        db.add(IoTData(device_id=stale.id, temperature=-18.0,
                       recorded_at=datetime.now() - timedelta(minutes=10)))
        db.commit()

        changed = mark_offline_devices(db, offline_seconds=90)

        status = {d.device_code: d.status for d in db.query(IoTDevice).all()}
    finally:
        db.close()

    assert changed == ["STALE"]
    assert status["STALE"] == "offline"
    assert status["LIVE"] == "online"


def test_mark_offline_when_never_reported(client, make_user):
    from app.database import SessionLocal
    from app.models import IoTDevice
    from app.tasks import mark_offline_devices

    sup = make_user(role="supplier")
    client.post("/api/devices", headers=sup["headers"], json={"device_code": "NEVER"})

    db = SessionLocal()
    try:
        db.query(IoTDevice).filter(IoTDevice.device_code == "NEVER").update(
            {"status": "online"}, synchronize_session=False
        )
        db.commit()
        changed = mark_offline_devices(db)
        dev = db.query(IoTDevice).filter(IoTDevice.device_code == "NEVER").one()
    finally:
        db.close()

    assert changed == ["NEVER"]
    assert dev.status == "offline"
