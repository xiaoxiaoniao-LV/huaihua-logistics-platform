"""供需匹配推荐：规则 + 加权评分（MVP 版本，后续可升级协同过滤/向量召回）。"""
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import Resource, User


def recommend(
    db: Session,
    *,
    resource_type: str | None = None,
    max_price: float | None = None,
    resource_id: int | None = None,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """对当前市场上的 available 资源打分排序，返回 top N。

    打分维度（权重可调）：
      - 状态匹配（available 才入选，占 0 分基线）
      - 价格友好（低价 = 高分） 0-30
      - 供给方信用（credit_score 越高越好）0-20
      - 时间窗口覆盖（资源 available_start/end 覆盖范围越宽越好）0-20
      - 标签匹配（如指定 resource_type 完全命中 +10）10
    """
    query = db.query(Resource).filter(Resource.status == "available")
    if resource_type:
        query = query.filter(Resource.type == resource_type)
    if max_price is not None:
        query = query.filter(Resource.price <= max_price)

    candidates = query.limit(200).all()
    if not candidates:
        return []

    # 价格归一化：最低分 30，线性递减到 0（用 lo/hi 避免遮蔽入参 max_price）
    prices = [float(r.price or 0) for r in candidates]
    lo, hi = min(prices), max(prices)
    price_range = max(1e-6, hi - lo)

    # 信用分归一化：假设 80-100 为正常区间
    credits = {}
    user_ids = list({c.user_id for c in candidates})
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    for u in users:
        credits[u.id] = u.credit_score

    now = datetime.now()
    # scored: (总分, 分项得分 dict, Resource)
    scored: list[tuple[float, dict[str, float], Resource]] = []
    for r in candidates:
        bd = {"price_score": 0.0, "credit_score": 0.0, "window_score": 0.0, "type_match": 0.0}
        s = 0.0
        # 价格得分 0-30
        if r.price is not None:
            p = float(r.price)
            ps = max(0.0, 30.0 * (1 - (p - lo) / price_range))
            bd["price_score"] = ps
            s += ps
        # 信用得分 0-20
        cr = credits.get(r.user_id, 100)
        cs = 20.0 * max(0.0, min(1.0, (cr - 60) / 40))
        bd["credit_score"] = cs
        s += cs
        # 时间窗口得分 0-20
        if r.available_start and r.available_end:
            span_days = max(0.0, (r.available_end - max(r.available_start, now)).total_seconds() / 86400)
            ws = min(20.0, span_days * 2.0)
            bd["window_score"] = ws
            s += ws
        # 类型匹配加分 0/10
        if resource_type:
            bd["type_match"] = 10.0
            s += 10.0
        scored.append((s, bd, r))

    scored.sort(key=lambda x: -x[0])

    out = []
    for score, bd, r in scored[:top_n]:
        out.append({
            "resource_id": r.id,
            "name": r.name,
            "type": r.type,
            "price": float(r.price) if r.price is not None else None,
            "price_unit": r.price_unit,
            "location": r.location,
            "status": r.status,
            "match_score": round(score, 2),
            "score_breakdown": {
                "price_score": round(bd["price_score"], 2),
                "credit_score": round(bd["credit_score"], 2),
                "window_score": round(bd["window_score"], 2),
                "type_match": round(bd["type_match"], 2),
            },
        })
    return out
