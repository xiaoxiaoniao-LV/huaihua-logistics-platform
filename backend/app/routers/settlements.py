"""结算单与对账：运营确认/打款，按日汇总 GMV、佣金与回款。

除逐单管理外，还提供两类运营能力：
- 租户分账：按供给方聚合结算笔数、金额、佣金、应付与已付/待付；
- 结算凭证：按结算单生成单页 A4 发票 PDF（零第三方依赖）。
"""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_admin_user, get_current_user
from ..models import Order, PaymentEvent, Settlement, User
from ..schemas.settlement import SettlementOut
from ..services.invoice_pdf import render_invoice_pdf

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


@router.get("/split")
def settlement_split(
    start: date | None = Query(None),
    end: date | None = Query(None),
    current: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """租户分账：按供给方聚合结算笔数/金额/佣金/应付，并区分已付与待付。

    作废（void）的结算单不计入分账；不传日期则统计全部历史。
    """
    paid_expr = func.coalesce(
        func.sum(case((Settlement.status == "paid", Settlement.payable_to_supplier), else_=0)), 0
    )
    due_expr = func.coalesce(
        func.sum(
            case(
                (Settlement.status.in_({"pending", "confirmed"}), Settlement.payable_to_supplier),
                else_=0,
            )
        ),
        0,
    )
    q = db.query(
        Settlement.supplier_id,
        func.count(Settlement.id),
        func.coalesce(func.sum(Settlement.amount), 0),
        func.coalesce(func.sum(Settlement.commission), 0),
        func.coalesce(func.sum(Settlement.payable_to_supplier), 0),
        paid_expr,
        due_expr,
    ).filter(Settlement.status != "void")
    if start:
        q = q.filter(Settlement.created_at >= datetime.combine(start, time.min))
    if end:
        q = q.filter(Settlement.created_at < datetime.combine(end, time.min) + timedelta(days=1))
    rows = q.group_by(Settlement.supplier_id).all()

    names = {
        uid: (company or username)
        for uid, company, username in db.query(User.id, User.company_name, User.username)
        .filter(User.id.in_([r[0] for r in rows] or [0]))
        .all()
    }

    items = [
        {
            "supplier_id": sid,
            "supplier_name": names.get(sid) or f"供给方 #{sid}",
            "settlements": int(cnt),
            "amount": float(amount or 0),
            "commission": float(commission or 0),
            "payable": float(payable or 0),
            "paid": float(paid or 0),
            "unpaid": float(due or 0),
        }
        for sid, cnt, amount, commission, payable, paid, due in rows
    ]
    items.sort(key=lambda it: it["amount"], reverse=True)

    def _total(key: str) -> float:
        return round(sum(it[key] for it in items), 2)

    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "suppliers": len(items),
        "items": items,
        "total": {
            "settlements": sum(it["settlements"] for it in items),
            "amount": _total("amount"),
            "commission": _total("commission"),
            "payable": _total("payable"),
            "paid": _total("paid"),
            "unpaid": _total("unpaid"),
        },
    }


@router.get("/{settlement_id}/invoice.pdf")
def download_invoice(
    settlement_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """下载结算凭证（单页 A4 发票 PDF）。

    管理员可下载任意结算单，供给方只能下载自己的；已作废的结算单不再开票。
    """
    s = db.query(Settlement).filter(Settlement.id == settlement_id).first()
    if s is None:
        raise HTTPException(404, "结算单不存在")
    if current.role != "admin" and current.id != s.supplier_id:
        raise HTTPException(403, "无权查看该结算单的开票凭证")
    if s.status == "void":
        raise HTTPException(400, "已作废的结算单不能开票")

    order = db.query(Order).filter(Order.id == s.order_id).first()
    supplier = db.query(User).filter(User.id == s.supplier_id).first()
    buyer = (
        db.query(User).filter(User.id == order.demander_id).first() if order else None
    )
    issued_at = s.settled_at or s.created_at or datetime.now()

    pdf = render_invoice_pdf(
        invoice_no=f"JS{issued_at:%Y%m%d}{s.id:06d}",
        issued_at=issued_at,
        seller_name=settings.invoice_seller_name,
        seller_tax_no=settings.invoice_seller_tax_no,
        buyer_name=(supplier.company_name if supplier else None)
        or (supplier.username if supplier else f"供给方 #{s.supplier_id}"),
        buyer_tax_no="",
        item_name="冷链资源撮合服务费",
        note=(
            f"结算单 #{s.id} · 订单 ORD{s.order_id:08d} · "
            f"订单金额 ¥{float(s.amount):,.2f} · 应付 ¥{float(s.payable_to_supplier):,.2f}"
            + (f" · 需求方 {buyer.company_name or buyer.username}" if buyer else "")
        ),
        amount=float(s.commission or 0),
        tax_rate=settings.invoice_tax_rate,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{s.id}.pdf"'},
    )


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
