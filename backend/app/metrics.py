"""Prometheus 指标：HTTP 请求、IoT 入库量与业务积压。

`/metrics` 供 Prometheus 抓取；数据库类指标在抓取时即时聚合，
避免引入额外的后台聚合协程。
"""
import time

from fastapi import Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Histogram,
    generate_latest,
)
from prometheus_client.metrics_core import GaugeMetricFamily

HTTP_REQUESTS = Counter(
    "hhlg_http_requests_total",
    "HTTP 请求数",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "hhlg_http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.3, 0.5, 1, 2, 5, 10),
)
IOT_MESSAGES = Counter(
    "hhlg_iot_messages_total",
    "MQTT 遥测消息入库条数",
)


class BusinessCollector:
    """抓取时聚合 outbox / 设备 / 活动告警，供积压告警使用。"""

    def collect(self):
        from sqlalchemy import func

        from .database import SessionLocal
        from .models import Alert, IoTDevice, OutboxEvent

        outbox = GaugeMetricFamily(
            "hhlg_outbox_events", "事务外盒事件数（按状态）", labels=["status"]
        )
        devices = GaugeMetricFamily(
            "hhlg_iot_devices", "设备数（按状态）", labels=["status"]
        )
        active_alerts = GaugeMetricFamily(
            "hhlg_alerts_active", "未恢复的活动告警数"
        )

        db = SessionLocal()
        try:
            rows = (
                db.query(OutboxEvent.status, func.count())
                .group_by(OutboxEvent.status)
                .all()
            )
            for status, count in rows:
                outbox.add_metric([status or "unknown"], count)

            rows = (
                db.query(IoTDevice.status, func.count())
                .group_by(IoTDevice.status)
                .all()
            )
            for status, count in rows:
                devices.add_metric([status or "unknown"], count)

            active = (
                db.query(func.count(Alert.id)).filter(Alert.status == "active").scalar()
            )
            active_alerts.add_metric([], active or 0)
        except Exception:  # 数据库短暂不可用时不影响指标抓取
            return
        finally:
            db.close()

        yield outbox
        yield devices
        yield active_alerts


REGISTRY.register(BusinessCollector())


async def prometheus_middleware(request: Request, call_next):
    """记录每个请求的计数与耗时；路径使用路由模板，避免基数爆炸。"""
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", None) or "unmatched"
        HTTP_REQUESTS.labels(request.method, path, status).inc()
        HTTP_DURATION.labels(request.method, path).observe(time.perf_counter() - start)


def render_metrics() -> bytes:
    return generate_latest(REGISTRY)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "IOT_MESSAGES",
    "prometheus_middleware",
    "render_metrics",
]
