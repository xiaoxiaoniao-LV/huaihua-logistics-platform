"""撮合评分。"""


def _mk(make_resource, owner, price, **kw):
    return make_resource(owner, status="available", price=price, name=f"箱{price}", **kw)


def test_recommend_returns_breakdown_sorted_by_score(client, make_user, make_resource):
    sup = make_user(role="supplier")
    _mk(make_resource, sup, "50.00")
    _mk(make_resource, sup, "100.00")
    _mk(make_resource, sup, "200.00")

    r = client.get("/api/match/recommend", params={"type": "cold_box", "top_n": 3})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 3

    prices = [float(x["price"]) for x in results]
    assert prices == sorted(prices)  # 价格越低分越高，50 在前

    first, last = results[0], results[-1]
    assert first["score_breakdown"]["price_score"] == 30.0
    assert last["score_breakdown"]["price_score"] == 0.0
    # 信用分默认 100 → 满分 20
    assert first["score_breakdown"]["credit_score"] == 20.0
    # 指定类型命中 +10
    assert first["score_breakdown"]["type_match"] == 10.0
    assert first["match_score"] > last["match_score"]


def test_recommend_respects_max_price_filter(client, make_user, make_resource):
    """回归：入参 max_price 曾被局部变量遮蔽，导致价格过滤失效。"""
    sup = make_user(role="supplier")
    _mk(make_resource, sup, "50.00")
    _mk(make_resource, sup, "100.00")
    _mk(make_resource, sup, "300.00")

    r = client.get("/api/match/recommend", params={"type": "cold_box", "max_price": 120, "top_n": 10})
    prices = [float(x["price"]) for x in r.json()["results"]]
    assert len(prices) == 2
    assert max(prices) <= 120


def test_recommend_excludes_non_available(client, make_user, make_resource):
    sup = make_user(role="supplier")
    make_resource(sup)  # pending，不可预约
    _mk(make_resource, sup, "80.00")

    r = client.get("/api/match/recommend", params={"type": "cold_box", "top_n": 10})
    results = r.json()["results"]
    assert len(results) == 1
    assert float(results[0]["price"]) == 80.0


def test_recommend_empty_when_no_available(client, make_user, make_resource):
    sup = make_user(role="supplier")
    make_resource(sup)
    r = client.get("/api/match/recommend", params={"type": "cold_box"})
    assert r.json()["count"] == 0
