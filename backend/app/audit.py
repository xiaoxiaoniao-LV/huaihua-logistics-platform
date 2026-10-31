"""审计日志埋点工具。

在关键操作后调用 log_audit，把「谁、在何时、做了什么、针对哪个对象」写入 audit_logs 表，
供管理员在后台追溯。日志记录失败不应影响主流程，故吞掉异常。
"""
import logging

from sqlalchemy.orm import Session

from .models import AuditLog, User

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    user: User | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    try:
        entry = AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail[:255] if detail else None,
            ip=ip[:45] if ip else None,
        )
        db.add(entry)
        db.commit()
    except Exception as e:  # 审计失败不能阻断业务
        logger.warning("[audit] 写审计日志失败 action=%s: %s", action, e)
