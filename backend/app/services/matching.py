"""供需匹配推荐：规则 + 加权评分。

评分维度（合计满分 120）：
  - 价格友好（同类最低价 30 → 最高价 0）
  - 供给方信用（credit_score 60-100 映射 0-20）
  - 可租时间窗口（覆盖天数 × 2，上限 20）
  - 类型命中（指定 type 时 +10）
  - 供给方口碑（评价均分 3-5 映射 0-15，无评价给 9 分中性值）
  - 成交热度（近 30 天非取消订单数，按候选集最大值归一化，上限 10）
  - 上新程度（30 天内线性衰减，上限 5）
  - 个性化偏好（登录用户历史需求类型命中 +10）

同时输出中文推荐理由，便于前端展示“为什么推荐”。
"""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Order, Resource, Review, User

_TYPE_CN = {
    "warehouse": "冷库",
    "cold_box": "冷链箱位",
    "vehicle": "冷藏运输",
    "equipment": "温控设备",
}

_HOT_WINDOW_DAYS = 30
_PREF_HISTORY_LIMIT = 50


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _supplier_ratings(db: Session, supplier_ids: list[int]) -> dict[int, tuple[float, int]]:
    """供给方收到的评价：{user_id: (平均分, 评价条数)}。"""
    rows = (
        db.query(Review.to_user_id, func.avg(Review.rating), func.count(Review.id))
        .filter(Review.to_user_id.in_(supplier_ids))
        .group_by(Review.to_user_id)
        .all()
    )
    return {uid: (float(avg or 0), int(cnt or 0)) for uid, avg, cnt in rows}


def _supplier_hotness(db: Session, supplier_ids: list[int], since: datetime) -> dict[int, int]:
    """近 N 天成交热度：{user_id: 订单数}。"""
    rows = (
        db.query(Order.supplier_id, func.count(Order.id))
        .filter(
            Order.supplier_id.in_(supplier_ids),
            Order.created_at >= since,
            Order.status != "cancelled",
        )
        .group_by(Order.supplier_id)
        .all()
    )
    return {uid: int(cnt or 0) for uid, cnt in rows}


def _preferred_types(db: Session, user_id: int) -> set[str]:
    """登录用户历史下单过的资源类型，作为个性化偏好。"""
    rows = (
        db.query(Resource.type)
        .join(Order, Order.resource_id == Resource.id)
        .filter(Order.demander_id == user_id)
        .order_by(Order.id.desc())
        .limit(_PREF_HISTORY_LIMIT)
        .all()
    )
    return {t for (t,) in rows if t}


def recommend(
    db: Session,
    *,
    resource_type: str | None = None,
    max_price: float | None = None,
    resource_id: int | None = None,
    top_n: int = 5,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """对当前市场上的 available 资源打分排序，返回 top N。"""
    query = db.query(Resource).filter(Resource.status == "available")
    if resource_type:
        query = query.filter(Resource.type == resource_type)
    if max_price is not None:
        query = query.filter(Resource.price <= max_price)

    candidates = query.limit(200).all()
    if not candidates:
        return []

    now = datetime.now()

    # 价格归一化：最低分 30，线性递减到 0（用 lo/hi 避免遮蔽入参 max_price）
    prices = [float(r.price or 0) for r in candidates]
    lo, hi = min(prices), max(prices)
    price_range = max(1e-6, hi - lo)

    # 信用分归一化：假设 80-100 为正常区间
    supplier_ids = list({c.user_id for c in candidates})
    users = db.query(User).filter(User.id.in_(supplier_ids)).all()
    credits = {u.id: u.credit_score for u in users}

    ratings = _supplier_ratings(db, supplier_ids)
    hotness = _supplier_hotness(db, supplier_ids, now - timedelta(days=_HOT_WINDOW_DAYS))
    max_hot = max(hotness.values(), default=0) or 1
    preferred = _preferred_types(db, user_id) if user_id else set()

    # scored: (总分, 分项得分 dict, 理由列表, Resource)
    scored: list[tuple[float, dict[str, float], list[str], Resource]] = []
    for r in candidates:
        bd = {
            "price_score": 0.0,
            "credit_score": 0.0,
            "window_score": 0.0,
            "type_match": 0.0,
            "rating_score": 0.0,
            "hotness_score": 0.0,
            "freshness_score": 0.0,
            "preference_score": 0.0,
        }
        reasons: list[str] = []
        s = 0.0

        # 价格得分 0-30
        if r.price is not None:
            p = float(r.price)
            ps = max(0.0, 30.0 * (1 - (p - lo) / price_range))
            bd["price_score"] = ps
            s += ps
            if price_range > 1e-6 and p <= lo + price_range / 3:
                reasons.append("价格为同类最低档")

        # 信用得分 0-20
        cr = credits.get(r.user_id, 100)
        cs = 20.0 * _clamp((cr - 60) / 40)
        bd["credit_score"] = cs
        s += cs
        if cr >= 95:
            reasons.append(f"供给方信用分 {cr:.0f}")

        # 时间窗口得分 0-20
        if r.available_start and r.available_end:
            span_days = max(0.0, (r.available_end - max(r.available_start, now)).total_seconds() / 86400)
            ws = min(20.0, span_days * 2.0)
            bd["window_score"] = ws
            s += ws
            if span_days >= 7:
                reasons.append(f"可租窗口覆盖 {span_days:.0f} 天")

        # 类型匹配加分 0/10
        if resource_type:
            bd["type_match"] = 10.0
            s += 10.0

        # 口碑 0-15：均分 3 分 → 0，5 分 → 15；无评价给 9 分中性值
        avg_rating, review_cnt = ratings.get(r.user_id, (0.0, 0))
        if review_cnt:
            rs = 15.0 * _clamp((avg_rating - 3) / 2)
            bd["rating_score"] = rs
            s += rs
            if avg_rating >= 4.5:
                reasons.append(f"供给方口碑 {avg_rating:.1f} 分（{review_cnt} 条评价）")
        else:
            bd["rating_score"] = 9.0
            s += 9.0

        # 成交热度 0-10
        hot_cnt = hotness.get(r.user_id, 0)
        hs = 10.0 * min(1.0, hot_cnt / max_hot)
        bd["hotness_score"] = hs
        s += hs
        if hot_cnt >= 5:
            reasons.append(f"近 {_HOT_WINDOW_DAYS} 天成交 {hot_cnt} 单")

        # 上新程度 0-5：30 天内线性衰减
        if r.created_at:
            age_days = max(0.0, (now - r.created_at).total_seconds() / 86400)
            fs = 5.0 * _clamp(1 - age_days / 30)
            bd["freshness_score"] = fs
            s += fs
            if age_days <= 3:
                reasons.append("新上架资源")

        # 个性化偏好 0/10
        if r.type in preferred:
            bd["preference_score"] = 10.0
            s += 10.0
            reasons.append(f"符合你的历史偏好（{_TYPE_CN.get(r.type, r.type)}）")

        scored.append((s, bd, reasons, r))

    scored.sort(key=lambda x: (-x[0], float(x[3].price or 0)))

    out = []
    for score, bd, reasons, r in scored[:top_n]:
        out.append({
            "resource_id": r.id,
            "name": r.name,
            "type": r.type,
            "price": float(r.price) if r.price is not None else None,
            "price_unit": r.price_unit,
            "location": r.location,
            "status": r.status,
            "match_score": round(score, 2),
            "score_breakdown": {k: round(v, 2) for k, v in bd.items()},
            "reasons": reasons,
        })
    return out
