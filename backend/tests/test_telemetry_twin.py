"""遥测窄表接入、告警去抖与数字孪生读模型。"""
from datetime import datetime, timedelta

DEVICE_TOKEN = {"X-Device-Token": "test-device-token"}


def _ts(offset_seconds: int = 0) -> str:
    """统一用「5 分钟前 + 偏移」的秒级时间戳，避免用例受执行耗时影响。"""
    base = datetime.now().replace(microsecond=0) - timedelta(minutes=5)
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def _ingest(client, code: str, points: dict, ts: str | None = None,
            quality: str = "good", headers: dict | None = None):
    return client.post(
        "/api/v1/iot/telemetry",
        headers=DEVICE_TOKEN if headers is None else headers,
        json={"items": [{
            "device_code": code, "ts": ts, "quality": quality, "points": points,
        }]},
    )


# ---------------- 点位字典与批量写入 ----------------

def test_telemetry_requires_device_token(client):
    body = {"items": [{"device_code": "TL-0", "points": {"temp_in": -18.0}}]}
    assert client.post("/api/v1/iot/telemetry", json=body).status_code == 401
    assert client.post("/api/v1/iot/telemetry", json=body,
                       headers={"X-Device-Token": "wrong"}).status_code == 401
    assert client.post("/api/v1/iot/telemetry", json=body,
                       headers=DEVICE_TOKEN).status_code == 201


def test_unknown_point_rejected_and_device_rolled_back(client):
    r = _ingest(client, "TL-1", {"temp_in": -18.0, "unknown_sensor": 1})
    assert r.status_code == 400
    assert "unknown_sensor" in r.json()["detail"]
    # 整批回滚，设备与点位都不应残留
    assert client.get("/api/v1/iot/devices/TL-1/points").status_code == 404


def test_ingest_autoregisters_points_and_state(client):
    r = _ingest(client, "TL-2", {"temp_in": -18.5, "hum_in": 60, "door": False}, _ts())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["accepted"] == 3 and body["duplicates"] == 0
    summary = body["devices"][0]
    assert summary["status"] == "online" and summary["quality"] == "good"

    points = client.get("/api/v1/iot/devices/TL-2/points").json()
    assert {p["point_key"] for p in points["points"]} == {"temp_in", "hum_in", "door"}
    temp = next(p for p in points["points"] if p["point_key"] == "temp_in")
    assert temp["unit"] == "℃" and temp["max_value"] == -5.0

    state = client.get("/api/v1/iot/devices/TL-2/state").json()
    values = {p["point_key"]: p["value"] for p in state["points"]}
    assert values["temp_in"] == -18.5
    assert values["hum_in"] == 60.0
    assert values["door"] is False
    assert state["status"] == "online" and state["quality"] == "good"
    assert state["age_ms"] is not None and state["age_ms"] > 0


def test_replay_same_timestamp_is_idempotent(client):
    ts = _ts()
    first = _ingest(client, "TL-3", {"temp_in": -18.0}, ts).json()
    assert first["accepted"] == 1

    second = _ingest(client, "TL-3", {"temp_in": -18.0}, ts).json()
    assert second["accepted"] == 0 and second["duplicates"] == 1

    series = client.get("/api/v1/iot/devices/TL-3/series",
                        params={"point_key": "temp_in"}).json()
    assert series["count"] == 1


def test_series_is_time_ordered(client):
    _ingest(client, "TL-4", {"temp_in": -18.0}, _ts(0))
    _ingest(client, "TL-4", {"temp_in": -17.0}, _ts(60))
    _ingest(client, "TL-4", {"temp_in": -16.0}, _ts(120))

    series = client.get("/api/v1/iot/devices/TL-4/series",
                        params={"point_key": "temp_in"}).json()
    assert series["unit"] == "℃"
    assert [row["value"] for row in series["data"]] == [-18.0, -17.0, -16.0]
    assert series["data"][0]["ts"] < series["data"][-1]["ts"]

    assert client.get("/api/v1/iot/devices/TL-4/series",
                      params={"point_key": "not_exist"}).status_code == 404


def test_bad_quality_marks_device_degraded(client):
    r = _ingest(client, "TL-5", {"temp_in": -18.0}, _ts(0), quality="bad")
    summary = r.json()["devices"][0]
    assert summary["status"] == "degraded" and summary["quality"] == "bad"

    r = _ingest(client, "TL-5", {"temp_in": -18.0}, _ts(10), quality="good")
    summary = r.json()["devices"][0]
    assert summary["status"] == "online" and summary["quality"] == "good"

    assert _ingest(client, "TL-5", {"temp_in": -18.0}, _ts(20),
                   quality="rotten").status_code == 422


def test_admin_can_register_custom_point(client, make_user):
    admin = make_user(role="admin")
    _ingest(client, "TL-6", {"temp_in": -18.0}, _ts())

    payload = {"point_key": "light_lux", "name": "光照", "unit": "lux",
               "data_type": "number", "precision": 0, "min_value": 0, "max_value": 2000}
    assert client.post("/api/v1/iot/devices/TL-6/points",
                       json=payload).status_code == 401
    assert client.post("/api/v1/iot/devices/TL-6/points",
                       headers=make_user()["headers"], json=payload).status_code == 403

    r = client.post("/api/v1/iot/devices/TL-6/points",
                    headers=admin["headers"], json=payload)
    assert r.status_code == 201 and r.json()["point_key"] == "light_lux"
    assert client.post("/api/v1/iot/devices/TL-6/points",
                       headers=admin["headers"], json=payload).status_code == 400

    keys = {p["point_key"] for p in
            client.get("/api/v1/iot/devices/TL-6/points").json()["points"]}
    assert {"temp_in", "light_lux"} <= keys


# ---------------- 告警去抖 ----------------

def test_alarm_debounce_and_auto_recovery(client):
    # 前两次越限只采样不告警，避免抖动刷屏
    for i in range(2):
        r = _ingest(client, "TL-7", {"temp_in": 10.0}, _ts(i))
        assert r.json()["devices"][0]["events"] == []
    assert client.get("/api/v1/iot/alerts", params={"status": "active"}).json()["count"] == 0

    # 连续第三次越限才真正告警
    r = _ingest(client, "TL-7", {"temp_in": 10.0}, _ts(2))
    events = r.json()["devices"][0]["events"]
    assert len(events) == 1
    assert events[0]["kind"] == "alarm"
    assert events[0]["point_key"] == "temp_in"
    assert events[0]["direction"] == "high"
    assert events[0]["level"] == "critical"

    alerts = client.get("/api/v1/iot/alerts", params={"status": "active"}).json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["type"] == "temp_in_high" and alerts[0]["device_code"] == "TL-7"
    assert client.get("/api/v1/iot/devices/TL-7/state").json()["status"] == "alarm"

    # 回到正常区间：告警自动恢复，设备回到 online
    r = _ingest(client, "TL-7", {"temp_in": -18.0}, _ts(3))
    events = r.json()["devices"][0]["events"]
    assert events[0]["kind"] == "recovered" and events[0]["resolved_alerts"] == 1
    assert client.get("/api/v1/iot/alerts", params={"status": "active"}).json()["count"] == 0
    assert client.get("/api/v1/iot/devices/TL-7/state").json()["status"] == "online"

    unresolved = client.get("/api/v1/iot/devices/TL-7/events",
                            params={"unresolved": True}).json()
    assert unresolved["count"] == 0


def test_door_magnet_records_open_close(client):
    first = _ingest(client, "TL-8", {"door": False}, _ts(0)).json()
    assert first["devices"][0]["events"] == []

    opened = _ingest(client, "TL-8", {"door": True}, _ts(10)).json()
    assert opened["devices"][0]["events"][0]["kind"] == "door"
    assert opened["devices"][0]["events"][0]["open"] is True

    closed = _ingest(client, "TL-8", {"door": False}, _ts(20)).json()
    assert closed["devices"][0]["events"][0]["open"] is False

    events = client.get("/api/v1/iot/devices/TL-8/events").json()
    assert events["count"] == 2
    assert {e["event_type"] for e in events["events"]} == {"door_open", "door_close"}


# ---------------- 数字孪生 ----------------

def test_twin_tree_binding_and_node_status(client, make_user):
    admin = make_user(role="admin")
    _ingest(client, "TW-1", {"temp_in": -18.5}, _ts())

    root = client.post("/api/v1/twin/nodes", headers=admin["headers"], json={
        "node_key": "hh-port-coldroom-a", "name": "A 库", "node_type": "room",
    })
    assert root.status_code == 200 and root.json()["created"] is True
    root_id = root.json()["id"]

    child = client.post("/api/v1/twin/nodes", headers=admin["headers"], json={
        "node_key": "hh-port-coldroom-a-door", "name": "A 库门",
        "node_type": "zone", "parent_id": root_id,
    })
    assert child.status_code == 200 and child.json()["created"] is True

    bind = client.post("/api/v1/twin/bindings", headers=admin["headers"], json={
        "node_key": "hh-port-coldroom-a-door", "device_code": "TW-1",
        "point_key": "temp_in",
    })
    assert bind.status_code == 200 and bind.json()["created"] is True
    binding_id = bind.json()["id"]

    # 大屏可匿名只读
    tree = client.get("/api/v1/twin/tree").json()
    assert tree["count"] == 2
    assert tree["summary"]["online"] == 2
    root_node = tree["tree"][0]
    assert root_node["node_key"] == "hh-port-coldroom-a"
    assert len(root_node["children"]) == 1
    bound = root_node["children"][0]["bindings"][0]
    assert bound["value"] == -18.5 and bound["unit"] == "℃"
    assert bound["device_status"] == "online"

    # 重复绑定当更新处理
    again = client.post("/api/v1/twin/bindings", headers=admin["headers"], json={
        "node_key": "hh-port-coldroom-a-door", "device_code": "TW-1",
        "point_key": "temp_in", "binding_type": "status",
    }).json()
    assert again["created"] is False and again["binding_type"] == "status"

    # 节点按 node_key 幂等更新
    updated = client.post("/api/v1/twin/nodes", headers=admin["headers"], json={
        "node_key": "hh-port-coldroom-a", "name": "A 库（改造）", "node_type": "room",
    }).json()
    assert updated["created"] is False
    assert client.get("/api/v1/twin/nodes/hh-port-coldroom-a").json()["name"] == "A 库（改造）"

    assert client.delete(f"/api/v1/twin/bindings/{binding_id}",
                         headers=admin["headers"]).status_code == 204
    assert client.get("/api/v1/twin/tree").json()["tree"][0]["children"][0]["bindings"] == []


def test_twin_write_requires_admin_and_valid_refs(client, make_user):
    admin = make_user(role="admin")
    payload = {"node_key": "n1", "name": "节点", "node_type": "room"}
    assert client.post("/api/v1/twin/nodes", json=payload).status_code == 401
    assert client.post("/api/v1/twin/nodes",
                       headers=make_user()["headers"], json=payload).status_code == 403

    missing_parent = client.post("/api/v1/twin/nodes", headers=admin["headers"], json={
        "node_key": "n2", "name": "子节点", "node_type": "zone", "parent_id": 999999,
    })
    assert missing_parent.status_code == 404

    assert client.post("/api/v1/twin/nodes",
                       headers=admin["headers"], json=payload).status_code == 200
    _ingest(client, "TW-2", {"temp_in": -18.0}, _ts())
    bad_point = client.post("/api/v1/twin/bindings", headers=admin["headers"], json={
        "node_key": "n1", "device_code": "TW-2", "point_key": "not_registered",
    })
    assert bad_point.status_code == 400


def test_watchdog_uses_narrow_telemetry_timestamp(client):
    from app.database import SessionLocal
    from app.tasks import mark_offline_devices

    now = datetime.now().replace(microsecond=0)
    _ingest(client, "WL-1", {"temp_in": -18.0}, now.isoformat())

    db = SessionLocal()
    try:
        assert mark_offline_devices(db, now=now + timedelta(seconds=30),
                                    offline_seconds=90) == []
        assert mark_offline_devices(db, now=now + timedelta(seconds=200),
                                    offline_seconds=90) == ["WL-1"]
    finally:
        db.close()

    state = client.get("/api/v1/iot/devices/WL-1/state").json()
    assert state["status"] == "offline" and state["quality"] == "stale"


def test_snapshot_read_model_for_screen(client, make_user):
    admin = make_user(role="admin")
    _ingest(client, "SN-1", {"temp_in": -18.5, "door": False}, _ts())

    node = client.post("/api/v1/twin/nodes", headers=admin["headers"], json={
        "node_key": "sn-room", "name": "SN 库", "node_type": "room",
    }).json()
    client.post("/api/v1/twin/bindings", headers=admin["headers"], json={
        "node_key": "sn-room", "device_code": "SN-1", "point_key": "temp_in",
    })

    # 越限告警进入活动列表
    for i in range(3):
        _ingest(client, "SN-1", {"temp_in": -2.0}, _ts(10 + i))

    snap = client.get("/api/v1/twin/snapshot").json()
    assert snap["count"] == 1 and snap["summary"]["alarm"] == 1
    assert snap["devices"]["total"] == 1
    device = snap["devices"]["items"][0]
    assert device["device_code"] == "SN-1"
    assert device["point_count"] == 2 and device["status"] == "alarm"
    assert snap["alerts"]["count"] == 1
    assert snap["alerts"]["items"][0]["device_code"] == "SN-1"
    assert snap["events"]["count"] >= 1
    assert snap["generated_at"]
