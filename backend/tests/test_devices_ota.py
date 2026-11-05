"""设备批量导入与固件 OTA。"""
DEVICE_TOKEN = {"X-Device-Token": "test-device-token"}


def _csv(text: str) -> dict:
    return {"file": ("devices.csv", text.encode("utf-8"), "text/csv")}


def test_import_devices_csv(client, make_user, make_resource):
    admin = make_user(role="admin")
    res = make_resource(admin)

    body = (
        "device_code,device_type,resource_id,firmware_version\n"
        f"IMP-01,dht22,{res['id']},1.2.0\n"
        "IMP-02,gps,0,\n"
        "IMP-03,,,1.0.0\n"
    )
    r = client.post("/api/devices/import", headers=admin["headers"], files=_csv(body))
    assert r.status_code == 200, r.text
    data = r.json()
    assert (data["created"], data["skipped"], data["failed"]) == (3, 0, 0)
    assert data["errors"] == []

    devices = {d["device_code"]: d for d in client.get("/api/devices", headers=admin["headers"]).json()}
    assert devices["IMP-01"]["resource_id"] == res["id"]
    assert devices["IMP-01"]["firmware_version"] == "1.2.0"
    assert devices["IMP-02"]["firmware_version"] == "1.0.0"


def test_import_skips_existing_and_reports_errors(client, make_user):
    admin = make_user(role="admin")
    header = "device_code,device_type,resource_id,firmware_version\n"

    first = client.post("/api/devices/import", headers=admin["headers"],
                        files=_csv(header + "DUP-1,dht22,0,1.0.0\n"))
    assert first.json()["created"] == 1

    body = (
        header
        + "DUP-1,dht22,0,1.0.0\n"      # 已存在 → 跳过
        + "NEW-2,dht22,0,1.0.0\n"      # 新增
        + "NEW-2,dht22,0,1.0.0\n"      # 文件内重复 → 失败
        + ",,,\n"                       # 缺编码 → 失败
        + "BAD-RES,dht22,999999,1.0.0\n"  # 资源不存在 → 失败
    )
    r = client.post("/api/devices/import", headers=admin["headers"], files=_csv(body))
    assert r.status_code == 200, r.text
    data = r.json()
    assert (data["created"], data["skipped"], data["failed"]) == (1, 1, 3)
    reasons = " ".join(e["reason"] for e in data["errors"])
    assert "文件内编码重复" in reasons
    assert "不能为空" in reasons
    assert "不存在" in reasons


def test_import_requires_admin_and_valid_header(client, make_user):
    demander = make_user()
    r = client.post("/api/devices/import", headers=demander["headers"],
                    files=_csv("device_code\nX-1\n"))
    assert r.status_code == 403

    admin = make_user(role="admin")
    r = client.post("/api/devices/import", headers=admin["headers"],
                    files=_csv("code,type\nA,B\n"))
    assert r.status_code == 400
    assert "device_code" in r.json()["detail"]


def test_ota_job_and_device_report(client, make_user):
    admin = make_user(role="admin")
    created = client.post("/api/devices", headers=admin["headers"], json={
        "device_code": "OTA-1", "device_type": "dht22", "resource_id": 0,
    })
    assert created.status_code == 201, created.text
    device = created.json()
    assert device["firmware_version"] == "1.0.0"

    r = client.post("/api/devices/ota", headers=admin["headers"],
                    json={"target_version": "1.1.0", "device_ids": [device["id"]]})
    assert r.status_code == 200, r.text
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["status"] in ("pending", "running")
    assert tasks[0]["from_version"] == "1.0.0"

    # 设备回执
    rep = client.post("/api/devices/ota/report", headers=DEVICE_TOKEN, json={
        "device_code": "OTA-1", "target_version": "1.1.0",
        "success": True, "message": "done",
    })
    assert rep.status_code == 200, rep.text
    assert rep.json()["status"] == "success"
    assert rep.json()["firmware_version"] == "1.1.0"

    listed = client.get("/api/devices", headers=admin["headers"]).json()
    assert next(d for d in listed if d["device_code"] == "OTA-1")["firmware_version"] == "1.1.0"

    # 已完成升级的设备再次下发同一版本时跳过
    r = client.post("/api/devices/ota", headers=admin["headers"],
                    json={"target_version": "1.1.0", "device_ids": [device["id"]]})
    assert r.status_code == 200
    assert r.json() == []

    tasks = client.get("/api/devices/ota", headers=admin["headers"]).json()
    assert tasks[0]["status"] == "success"
    assert tasks[0]["device_code"] == "OTA-1"


def test_ota_report_rejects_bad_token(client, make_user):
    make_user(role="admin")
    r = client.post("/api/devices/ota/report", headers={"X-Device-Token": "wrong"}, json={
        "device_code": "OTA-1", "target_version": "1.1.0", "success": True,
    })
    assert r.status_code == 401
