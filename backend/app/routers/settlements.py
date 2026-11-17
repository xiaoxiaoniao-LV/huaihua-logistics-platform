"""结算单与对账：运营确认/打款，按日汇总 GMV、佣金与回款。"""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_admin_user, get_current_user
from ..models import Order, PaymentEvent, Settlement, User
from ..schemas.settlement import SettlementOut

router = APIRouter(prefix="/api/v1/settlements", tags=["settlements"])

# 结算单状态流转：pending → confirmed → paid；未打款前可 void
_TRANSITIONS = {
    "pending": {"confirmed", "void"},
    "confirmed": {"paid", "void"},
    "paid": set(),
    "void": set(),
}


@router.get("", response_model=list[SettlementOut])
def list_settlements(
    response: Response,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Settlement)
    if current.role != "admin":
        q = q.filter(Settlement.supplier_id == current.id)
    if status:
        q = q.filter(Settlement.status == status)
    response.headers["X-Total-Count"] = str(q.count())
    return (
        q.order_by(Settlement.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


@router.get("/reconciliation")
def reconciliation(
    day: date | None = Query(None),
    current: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """按日对账：订单 GMV、佣金、支付回款、待打款结算。"""
    target = day or date.today()
    start = datetime.combine(target, time.min)
    end = start + timedelta(days=1)

    order_q = db.query(Order).filter(Order.created_at >= start, Order.created_at < end)
    order_count = order_q.count()
    gmv = order_q.with_entities(func.coalesce(func.sum(Order.total_price), 0)).scalar()
    commission = order_q.with_entities(
        func.coalesce(func.sum(Order.commission), 0)
    ).scalar()

    paid = (
        db.query(func.coalesce(func.sum(PaymentEvent.amount), 0))
        .filter(
            PaymentEvent.event_type == "paid",
            PaymentEvent.created_at >= start,
            PaymentEvent.created_at < end,
        )
        .scalar()
    )

    pending_q = db.query(Settlement).filter(Settlement.status.in_({"pending", "confirmed"}))
    pending_count = pending_q.count()
    pending_amount = pending_q.with_entities(
        func.coalesce(func.sum(Settlement.payable_to_supplier), 0)
    ).scalar()

    return {
        "day": target.isoformat(),
        "orders": order_count,
        "gmv": float(gmv or 0),
        "commission": float(commission or 0),
        "paid_amount": float(paid or 0),
        "pending_settlements": pending_count,
        "pending_payout": float(pending_amount or 0),
    }


@router.put("/{settlement_id}/status", response_model=SettlementOut)
def update_settlement_status(
    settlement_id: int,
    new_status: str = Query(...),
    remark: str | None = Query(None),
    current: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    s = (
        db.query(Settlement)
        .filter(Settlement.id == settlement_id)
        .with_for_update()
        .first()
    )
    if s is None:
        raise HTTPException(404, "结算单不存在")
    if new_status not in _TRANSITIONS.get(s.status, set()):
        raise HTTPException(400, f"不允许的结算状态流转：{s.status} → {new_status}")
    s.status = new_status
    if remark:
        s.remark = remark
    if new_status == "paid":
        s.settled_at = datetime.now()
    db.commit()
    db.refresh(s)
    return s
