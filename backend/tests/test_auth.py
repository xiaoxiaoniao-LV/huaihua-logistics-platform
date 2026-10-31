"""认证与用户管理。"""


def test_register_and_login(client):
    r = client.post("/api/auth/register", json={
        "username": "alice", "password": "Passw0rd123", "role": "demander",
    })
    assert r.status_code == 201
    assert r.json()["credit_score"] == 100
    assert r.json()["is_active"] is True

    r = client.post("/api/auth/login", json={"username": "alice", "password": "Passw0rd123"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_register_rejects_weak_password(client):
    # 纯字母
    r = client.post("/api/auth/register", json={"username": "b1", "password": "abcdefghij"})
    assert r.status_code == 422
    # 纯数字
    r = client.post("/api/auth/register", json={"username": "b2", "password": "1234567890"})
    assert r.status_code == 422
    # 太短
    r = client.post("/api/auth/register", json={"username": "b3", "password": "a1b2"})
    assert r.status_code == 422


def test_register_duplicate_username(client):
    client.post("/api/auth/register", json={"username": "dup", "password": "Passw0rd123"})
    r = client.post("/api/auth/register", json={"username": "dup", "password": "Passw0rd123"})
    assert r.status_code == 400


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"username": "bob", "password": "Passw0rd123"})
    r = client.post("/api/auth/login", json={"username": "bob", "password": "WrongPass123"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/users/me").status_code == 401
    assert client.get("/api/users/me", headers={"Authorization": "Bearer bogus"}).status_code == 401


def test_me_returns_profile(client, make_user):
    u = make_user()
    r = client.get("/api/users/me", headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["username"] == u["username"]


def test_admin_self_registration_blocked_when_admin_exists(client, make_user):
    make_user(role="admin")
    r = client.post("/api/auth/register", json={
        "username": "hacker", "password": "Passw0rd123", "role": "admin",
    })
    assert r.status_code == 403


def test_first_admin_registration_allowed(client):
    r = client.post("/api/auth/register", json={
        "username": "firstadmin", "password": "Passw0rd123", "role": "admin",
    })
    assert r.status_code == 201


def test_user_list_requires_admin(client, make_user):
    d = make_user()
    a = make_user(role="admin")
    assert client.get("/api/users", headers=d["headers"]).status_code == 403
    r = client.get("/api/users", headers=a["headers"])
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_admin_can_disable_and_user_is_blocked(client, make_user):
    admin = make_user(role="admin")
    u = make_user()
    r = client.put(f"/api/users/{u['id']}", headers=admin["headers"], json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    # 被禁用后即使令牌有效也拒绝
    assert client.get("/api/users/me", headers=u["headers"]).status_code == 403
    # 恢复后可访问
    client.put(f"/api/users/{u['id']}", headers=admin["headers"], json={"is_active": True})
    assert client.get("/api/users/me", headers=u["headers"]).status_code == 200


def test_admin_cannot_disable_self(client, make_user):
    admin = make_user(role="admin")
    r = client.put(f"/api/users/{admin['id']}", headers=admin["headers"], json={"is_active": False})
    assert r.status_code == 400


def test_user_update_me(client, make_user):
    u = make_user()
    r = client.put("/api/users/me", headers=u["headers"], json={"company_name": "新公司"})
    assert r.status_code == 200
    assert r.json()["company_name"] == "新公司"
