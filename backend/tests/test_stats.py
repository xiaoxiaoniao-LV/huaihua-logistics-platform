"""运营统计接口。"""
from datetime import datetime, timedelta


def _finished_order(client, make_user, make_resource):
    sup = make_user(role="supplier")
    dem = make_user()
    res = make_resource(sup, status="available")
    order = client.post("/api/orders", headers=dem["headers"], json={
        "resource_id": res["id"],
        "start_time": (datetime.now() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.now() + timedelta(days=2)).isoformat(),
    }).json()
    client.put(f"/api/orders/{order['id']}/status", headers=sup["headers"],
               params={"new_status": "finished"})
    return sup, dem, res, order


def test_stats_requires_admin(client, make_user):
    user = make_user()
    for path in ("/api/stats/overview", "/api/stats/trend", "/api/stats/resources"):
        assert client.get(path, headers=user["headers"]).status_code == 403
        assert client.get(path).status_code == 401


def test_stats_overview_counts(client, make_user, make_resource):
    admin = make_user(role="admin")
    sup, _dem, _res, order = _finished_order(client, make_user, make_resource)
    make_resource(sup)  # 另有一条待审核资源

    data = client.get("/api/stats/overview", headers=admin["headers"]).json()
    assert data["resources"]["total"] == 2
    assert data["resources"]["by_status"]["pending"] == 1
    assert data["orders"]["finished"] == 1
    assert data["revenue"]["finished_amount"] == float(order["total_price"])
    assert data["revenue"]["commission"] == round(float(order["total_price"]) * 0.10, 2)
    assert data["users"]["total"] >= 2
    assert data["devices"]["total"] == 0
    assert data["alerts"]["active"] == 0


def test_stats_trend_fills_every_day(client, make_user, make_resource):
    admin = make_user(role="admin")
    _finished_order(client, make_user, make_resource)

    data = client.get("/api/stats/trend", headers=admin["headers"], params={"days": 7}).json()
    assert data["days"] == 7 and len(data["items"]) == 7
    today = data["items"][-1]
    assert today["date"] == datetime.now().date().isoformat()
    assert today["orders"] == 1
    assert today["amount"] > 0
    # 其余日期补零
    assert all(item["orders"] == 0 for item in data["items"][:-1])


def test_stats_resource_breakdown(client, make_user, make_resource):
    admin = make_user(role="admin")
    _sup, _dem, res, order = _finished_order(client, make_user, make_resource)

    items = client.get("/api/stats/resources", headers=admin["headers"]).json()["items"]
    cold = next(i for i in items if i["type"] == res["type"])
    assert cold["total"] >= 1
    assert cold["finished_amount"] >= float(order["total_price"])
    assert 0 <= cold["utilization"] <= 1
