"""撮合评分。"""
from app.database import SessionLocal
from app.models import Order, Review


def _add_reviews(to_user_id: int, ratings: list[int]) -> None:
    with SessionLocal() as db:
        for rating in ratings:
            db.add(Review(order_id=1, from_user_id=999999, to_user_id=to_user_id, rating=rating))
        db.commit()


def _add_order(demander_id: int, supplier_id: int, resource_id: int) -> None:
    with SessionLocal() as db:
        db.add(Order(
            resource_id=resource_id, supplier_id=supplier_id,
            demander_id=demander_id, status="finished",
        ))
        db.commit()



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


def test_supplier_rating_boosts_ranking(client, make_user, make_resource):
    """口碑好的供给方在同等价格下应排更前，并给出推荐理由。"""
    good = make_user(role="supplier")
    plain = make_user(role="supplier")
    _add_reviews(good["id"], [5, 5, 5])
    _mk(make_resource, plain, "100.00")
    _mk(make_resource, good, "100.00")

    results = client.get("/api/match/recommend", params={"top_n": 10}).json()["results"]
    assert results[0]["price"] == 100.0
    assert results[0]["score_breakdown"]["rating_score"] == 15.0
    assert any("口碑" in x for x in results[0]["reasons"])
    # 无评价的一方拿中性分 9，低于满分 15
    assert results[1]["score_breakdown"]["rating_score"] == 9.0


def test_reasons_and_new_dimensions_present(client, make_user, make_resource):
    sup = make_user(role="supplier")
    _mk(make_resource, sup, "50.00")
    r = client.get("/api/match/recommend", params={"top_n": 5}).json()["results"][0]
    bd = r["score_breakdown"]
    for key in ("rating_score", "hotness_score", "freshness_score", "preference_score"):
        assert key in bd
    assert isinstance(r["reasons"], list)


def test_logged_in_user_gets_preference_bonus(client, make_user, make_resource):
    """历史下单过冷链箱位的用户，同类资源应获得偏好加分。"""
    demander = make_user(role="demander")
    sup = make_user(role="supplier")
    history = make_resource(sup, type="cold_box", price="100.00")
    _add_order(demander["id"], sup["id"], history["id"])

    _mk(make_resource, sup, "100.00", type="warehouse")
    _mk(make_resource, sup, "100.00", type="cold_box")

    results = client.get(
        "/api/match/recommend", params={"top_n": 10}, headers=demander["headers"]
    ).json()["results"]
    cold = next(x for x in results if x["type"] == "cold_box")
    warehouse = next(x for x in results if x["type"] == "warehouse")
    assert cold["score_breakdown"]["preference_score"] == 10.0
    assert warehouse["score_breakdown"]["preference_score"] == 0.0
    assert any("历史偏好" in x for x in cold["reasons"])
    assert results[0]["type"] == "cold_box"

    # 未登录时不带个性化加分
    anon = client.get("/api/match/recommend", params={"top_n": 10}).json()["results"]
    assert all(x["score_breakdown"]["preference_score"] == 0.0 for x in anon)
