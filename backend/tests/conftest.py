"""pytest 全局配置。

要点：
1. 必须在导入应用之前设置环境变量，因为配置在模块加载时读取。
2. 使用独立的测试库（默认 hhlg_test），不触碰开发库。
3. Redis 指向一个不可达端口，让缓存降级为 miss，保证用例结果确定。
4. TestClient 不进入 lifespan，因此不会启动 MQTT 订阅线程与事件循环注入。
"""
import os
from urllib.parse import urlparse

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "mysql+pymysql://root:root123456@127.0.0.1:3307/hhlg_test?charset=utf8mb4",
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# 指向不可达端口并显式设置极短超时：让缓存快速降级为 miss，测试不依赖 Redis
os.environ["REDIS_URL"] = (
    "redis://127.0.0.1:6399/0?socket_connect_timeout=0.05&socket_timeout=0.05"
)
os.environ["DEVICE_INGEST_TOKEN"] = "test-device-token"
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40

import pymysql  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def _ensure_database(url: str) -> None:
    """测试库不存在时自动创建。"""
    p = urlparse(url)
    db_name = p.path.lstrip("/").split("?")[0]
    conn = pymysql.connect(
        host=p.hostname, port=p.port or 3306, user=p.username,
        password=p.password, charset="utf8mb4", autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


_ensure_database(TEST_DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables(_schema):
    """每个用例结束后清空全部表，保证用例之间互不影响。"""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture()
def client():
    return TestClient(app)


_seq = {"n": 0}


def _next_name(prefix: str) -> str:
    _seq["n"] += 1
    return f"{prefix}{_seq['n']}"


@pytest.fixture()
def make_user(client):
    """注册并登录一个用户，返回 id / headers。"""
    def _make(role: str = "demander", password: str = "Passw0rd123"):
        username = _next_name(role[:3])
        r = client.post("/api/auth/register", json={
            "username": username, "password": password, "role": role,
            "company_name": f"{username}公司", "contact": "13800000000",
        })
        assert r.status_code == 201, r.text
        token = client.post("/api/auth/login", json={
            "username": username, "password": password,
        }).json()["access_token"]
        return {
            "id": r.json()["id"],
            "username": username,
            "password": password,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    return _make


@pytest.fixture()
def make_resource(client):
    """以指定用户身份发布资源，可指定状态。

    状态属于用例准备数据（非被测行为），直接改库绕过审核限制；
    审核规则本身由 test_resources_orders.py 中的用例单独覆盖。
    """
    from sqlalchemy import update

    from app.models import Resource

    def _make(owner, status: str | None = None, **overrides):
        payload = {
            "type": "cold_box", "name": _next_name("资源"),
            "location": "怀化A区", "price": "100.00", "price_unit": "元/天",
            "description": "测试资源",
        }
        payload.update(overrides)
        r = client.post("/api/resources", headers=owner["headers"], json=payload)
        assert r.status_code == 201, r.text
        res = r.json()
        if status and status != res["status"]:
            with engine.begin() as conn:
                conn.execute(
                    update(Resource).where(Resource.id == res["id"]).values(status=status)
                )
            res = client.get(f"/api/resources/{res['id']}").json()
        return res
    return _make
