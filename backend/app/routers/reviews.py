"""评价：订单完成后交易双方互评，并据此重算信用分。

信用分规则（确定性重算，避免增量漂移）：
    平均分 5 -> 100，平均分 1 -> 60，线性映射；无评价时保持 100。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Order, Review, User
from ..schemas.review import ReviewCreate, ReviewOut, UserRatingSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

_BASE_CREDIT = 60.0
_CREDIT_RANGE = 40.0


def _recalc_credit(db: Session, user_id: int) -> int:
    """按该用户收到的全部评价重算信用分。"""
    avg = (
        db.query(func.avg(Review.rating))
        .filter(Review.to_user_id == user_id)
        .scalar()
    )
    if avg is None:
        score = 100
    else:
        score = round(_BASE_CREDIT + _CREDIT_RANGE * (float(avg) - 1.0) / 4.0)
        score = max(0, min(100, score))
    user = db.get(User, user_id)
    if user is not None:
        user.credit_score = score
    return score


def _to_out(db: Session, r: Review) -> ReviewOut:
    author = db.get(User, r.from_user_id)
    out = ReviewOut.model_validate(r)
    out.from_username = author.username if author else None
    return out


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    data: ReviewCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, data.order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "订单不存在")
    if current.id not in (order.demander_id, order.supplier_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只有订单参与方可以评价")
    if order.status != "finished":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "订单完成后才能评价")

    exists = (
        db.query(Review)
        .filter(Review.order_id == order.id, Review.from_user_id == current.id)
        .first()
    )
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你已评价过该订单，不能重复评价")

    to_user_id = order.supplier_id if current.id == order.demander_id else order.demander_id
    review = Review(
        order_id=order.id,
        from_user_id=current.id,
        to_user_id=to_user_id,
        rating=data.rating,
        content=data.content,
    )
    db.add(review)
    db.flush()

    score = _recalc_credit(db, to_user_id)
    db.commit()
    db.refresh(review)
    logger.info(
        "[reviews] order=%s from=%s to=%s rating=%s -> 信用分 %s",
        order.id, current.id, to_user_id, data.rating, score,
    )
    return _to_out(db, review)


@router.get("/order/{order_id}", response_model=list[ReviewOut])
def list_order_reviews(
    order_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "订单不存在")
    if current.role != "admin" and current.id not in (order.demander_id, order.supplier_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无权查看该订单评价")
    rows = db.query(Review).filter(Review.order_id == order_id).order_by(Review.id).all()
    return [_to_out(db, r) for r in rows]


@router.get("/user/{user_id}", response_model=UserRatingSummary)
def user_rating_summary(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")

    rows = (
        db.query(Review)
        .filter(Review.to_user_id == user_id)
        .order_by(Review.created_at.desc())
        .limit(limit)
        .all()
    )
    total = db.query(func.count(Review.id)).filter(Review.to_user_id == user_id).scalar() or 0
    avg = db.query(func.avg(Review.rating)).filter(Review.to_user_id == user_id).scalar()

    return UserRatingSummary(
        user_id=user_id,
        count=int(total),
        average=round(float(avg), 2) if avg is not None else 0.0,
        credit_score=user.credit_score,
        reviews=[_to_out(db, r) for r in rows],
    )
