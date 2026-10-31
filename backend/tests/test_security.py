"""安全与账号：修改密码、刷新令牌、登录限流、审计日志。"""
from datetime import datetime, timedelta

DEVICE_TOKEN = {"X-Device-Token": "test-device-token"}


# ---------------- 修改密码 ----------------

def test_change_password_success(client, make_user):
    u = make_user(password="OldPass123")
    r = client.post("/api/auth/change-password", headers=u["headers"],
                    json={"old_password": "OldPass123", "new_password": "NewPass456"})
    assert r.status_code == 200

    # 旧密码失效，新密码可登录
    assert client.post("/api/auth/login", json={
        "username": u["username"], "password": "OldPass123"}).status_code == 401
    assert client.post("/api/auth/login", json={
        "username": u["username"], "password": "NewPass456"}).status_code == 200


def test_change_password_rejects_wrong_old(client, make_user):
    u = make_user(password="OldPass123")
    r = client.post("/api/auth/change-password", headers=u["headers"],
                    json={"old_password": "WrongOld999", "new_password": "NewPass456"})
    assert r.status_code == 400


def test_change_password_rejects_weak_new(client, make_user):
    u = make_user()
    r = client.post("/api/auth/change-password", headers=u["headers"],
                    json={"old_password": u["password"], "new_password": "allletters"})
    assert r.status_code == 422


def test_change_password_rejects_same(client, make_user):
    u = make_user(password="OldPass123")
    r = client.post("/api/auth/change-password", headers=u["headers"],
                    json={"old_password": "OldPass123", "new_password": "OldPass123"})
    assert r.status_code == 400


def test_change_password_requires_token(client):
    assert client.post("/api/auth/change-password", json={
        "old_password": "a", "new_password": "NewPass456"}).status_code == 401


# ---------------- 刷新令牌（无感续期） ----------------

def test_refresh_token_rotation(client, make_user):
    u = make_user()
    login = client.post("/api/auth/login", json={
        "username": u["username"], "password": u["password"]}).json()
    assert login["access_token"] and login["refresh_token"]

    r = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 200
    new_pair = r.json()
    assert new_pair["access_token"] and new_pair["refresh_token"]
    # 旋转后旧 refresh token 仍可验证（无状态），但新令牌可用于鉴权
    assert client.get("/api/users/me",
                      headers={"Authorization": f"Bearer {new_pair['access_token']}"}).status_code == 200


def test_refresh_rejects_access_token(client, make_user):
    u = make_user()
    login = client.post("/api/auth/login", json={
        "username": u["username"], "password": u["password"]}).json()
    r = client.post("/api/auth/refresh", json={"refresh_token": login["access_token"]})
    assert r.status_code == 401


def test_refresh_rejects_invalid(client):
    assert client.post("/api/auth/refresh", json={"refresh_token": "bogus"}).status_code == 401


# ---------------- 登录失败限流 ----------------

def test_login_failure_degrades_when_redis_down(client):
    """Redis 不可达时（测试环境）限流降级为放行：连续失败不 500，正确密码仍可登录。"""
    client.post("/api/auth/register", json={"username": "rate", "password": "Passw0rd123"})
    for _ in range(6):
        r = client.post("/api/auth/login", json={"username": "rate", "password": "Wrong9999"})
        assert r.status_code == 401
    assert client.post("/api/auth/login", json={
        "username": "rate", "password": "Passw0rd123"}).status_code == 200


def test_login_locked_returns_429(client, monkeypatch):
    import app.routers.auth as auth_mod

    client.post("/api/auth/register", json={"username": "locked", "password": "Passw0rd123"})
    monkeypatch.setattr(auth_mod, "_login_locked", lambda username: True)
    r = client.post("/api/auth/login", json={"username": "locked", "password": "Passw0rd123"})
    assert r.status_code == 429


def test_login_rejects_disabled_user(client, make_user):
    admin = make_user(role="admin")
    u = make_user()
    client.put(f"/api/users/{u['id']}", headers=admin["headers"], json={"is_active": False})
    r = client.post("/api/auth/login", json={"username": u["username"], "password": u["password"]})
    assert r.status_code == 403


# ---------------- 审计日志 ----------------

def _create_and_review_resource(client, make_user):
    sup = make_user(role="supplier")
    admin = make_user(role="admin")
    r = client.post("/api/resources", headers=sup["headers"], json={
        "type": "cold_box", "name": "审计箱", "location": "怀化A区",
        "price": 100, "price_unit": "元/天",
    })
    rid = r.json()["id"]
    client.post(f"/api/resources/{rid}/review", headers=admin["headers"], json={"approve": True})
    return admin


def test_audit_logs_recorded_and_queryable(client, make_user, make_resource):
    admin = _create_and_review_resource(client, make_user)

    # 用户禁用也产生审计
    u = make_user()
    client.put(f"/api/users/{u['id']}", headers=admin["headers"], json={"is_active": False})

    # 管理员可查询，按时间倒序
    r = client.get("/api/audit-logs", headers=admin["headers"], params={"page": 1, "page_size": 50})
    assert r.status_code == 200
    logs = r.json()
    actions = {log["action"] for log in logs}
    assert "resource_review" in actions
    assert "user_update" in actions
    assert "login" in actions  # 前面登录动作
    assert r.headers["x-total-count"]


def test_audit_logs_filter_by_action(client, make_user):
    admin = _create_and_review_resource(client, make_user)
    r = client.get("/api/audit-logs", headers=admin["headers"],
                   params={"action": "resource_review"})
    assert r.status_code == 200
    assert all(log["action"] == "resource_review" for log in r.json())


def test_audit_logs_requires_admin(client, make_user):
    u = make_user()
    assert client.get("/api/audit-logs", headers=u["headers"]).status_code == 403
    assert client.get("/api/audit-logs").status_code == 401


def test_alert_resolve_audited(client, make_user, make_resource):
    admin = make_user(role="admin")
    sup = make_user(role="supplier")
    res = make_resource(sup, status="available")
    client.post("/api/devices", headers=sup["headers"],
                json={"device_code": "AUD-1", "resource_id": res["id"]})
    client.post("/api/iot/data", headers=DEVICE_TOKEN,
                json={"device_code": "AUD-1", "temperature": 10.0})
    alert_id = client.get("/api/iot/alerts", params={"status": "active"}).json()["alerts"][0]["id"]

    client.post(f"/api/iot/alerts/{alert_id}/resolve", headers=admin["headers"])

    r = client.get("/api/audit-logs", headers=admin["headers"],
                   params={"action": "alert_resolve"})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["target_id"] == alert_id
