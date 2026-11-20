"""无硬件虚拟验收：只用 HTTP 遥测接口跑一遍冷链监控闭环。

覆盖：常态上报 → 连续越限触发高温告警 → 同批重放幂等 → 恢复正常自动关闭
→ 门磁开/关事件 → 设备状态与数据质量。

用法：
    python scripts/acceptance.py
    python scripts/acceptance.py --device SIM-ACC-01 --api http://127.0.0.1:8010

退出码 0 表示全部通过。真实 ESP32 接上后，把 --device 换成设备编码即可复跑。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _flow import FlowError, http_json, read_env, wait_health  # noqa: E402

NORMAL_TEMP = -18.0
HIGH_TEMP = -2.0          # 高于默认上限 -5℃，连续 3 次触发 temp_in 高温告警
NORMAL_HUMIDITY = 60.0


class Checker:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, bool(ok), detail))
        print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
        return bool(ok)

    def report(self) -> int:
        failed = [item for item in self.results if not item[1]]
        print(f"\n验收结果：{len(self.results) - len(failed)}/{len(self.results)} 通过")
        return 0 if not failed else 1


def envelope(device: str, ts: datetime, seq: int, temp: float, door: bool) -> dict:
    return {
        "device_code": device,
        "ts": ts.isoformat(),
        "seq": seq,
        "quality": "good",
        "firmware_version": "acc-test",
        "points": {
            "temp_in": temp,
            "hum_in": NORMAL_HUMIDITY,
            "door": door,
            "rssi": -60,
        },
    }


def post_batch(api: str, token: str | None, items: list[dict]) -> dict:
    """上报一批 envelope，把逐条摘要合并成一条，便于断言总量。"""
    status, data = http_json(
        api, "POST", "/api/v1/iot/telemetry", {"items": items}, device_token=token
    )
    if status != 201 or not isinstance(data, dict):
        raise FlowError(f"遥测上报失败 HTTP {status}：{data}")
    devices = data.get("devices") or []
    if not devices:
        raise FlowError(f"遥测返回缺少 devices：{data}")
    return {
        "device_code": devices[-1].get("device_code"),
        "status": devices[-1].get("status"),
        "quality": devices[-1].get("quality"),
        "last_seen_at": devices[-1].get("last_seen_at"),
        "accepted": sum(d.get("accepted", 0) for d in devices),
        "duplicates": sum(d.get("duplicates", 0) for d in devices),
        "events": [event for d in devices for event in (d.get("events") or [])],
    }


def active_alert_types(api: str, device: str) -> set[str]:
    status, data = http_json(api, "GET", "/api/v1/iot/alerts?status=active&limit=500")
    if status != 200 or not isinstance(data, dict):
        raise FlowError(f"查询告警失败 HTTP {status}：{data}")
    return {
        alert.get("type")
        for alert in data.get("alerts", [])
        if alert.get("device_code") == device
    }


def run(api: str, device: str, token: str | None) -> int:
    checker = Checker()

    try:
        wait_health(api, timeout=30, interval=2)
        checker.check("后端健康检查", True)
    except FlowError as exc:
        checker.check("后端健康检查", False, str(exc))
        return checker.report()

    # 所有时间戳落在最近 2 分钟内且严格递增，避免与上一次验收的样本交叉
    base_time = datetime.now().replace(microsecond=0) - timedelta(seconds=120)

    try:
        first = post_batch(
            api, token, [envelope(device, base_time, 1, NORMAL_TEMP, False)]
        )
        checker.check(
            "常态遥测落库",
            first.get("accepted", 0) >= 4 and first.get("status") == "online",
            f"accepted={first.get('accepted')} status={first.get('status')}",
        )

        over_limit = [
            envelope(device, base_time + timedelta(seconds=10 * idx), idx + 1, HIGH_TEMP, False)
            for idx in range(1, 4)
        ]
        resp = [post_batch(api, token, [item]) for item in over_limit]
        alarm_events = [
            event for item in resp for event in item.get("events", [])
            if event.get("kind") == "alarm"
        ]
        checker.check(
            "连续 3 次越限触发高温告警",
            any(
                event.get("point_key") == "temp_in" and event.get("direction") == "high"
                for event in alarm_events
            ),
            f"事件 {[e.get('point_key') for e in alarm_events]}",
        )
        checker.check(
            "设备状态切到 alarm",
            resp[-1].get("status") == "alarm",
            f"status={resp[-1].get('status')}",
        )
        checker.check(
            "活动告警列表出现 temp_in_high",
            "temp_in_high" in active_alert_types(api, device),
        )

        replay = post_batch(api, token, over_limit)
        checker.check(
            "同批重放幂等（不入库新数据）",
            replay.get("accepted") == 0 and replay.get("duplicates") == 12,
            f"accepted={replay.get('accepted')} duplicates={replay.get('duplicates')}",
        )
        checker.check(
            "重放后告警状态不变",
            resp[-1].get("status") == "alarm" and replay.get("status") == "alarm",
            f"status={replay.get('status')}",
        )

        recovered = post_batch(
            api, token,
            [envelope(device, base_time + timedelta(seconds=40), 5, NORMAL_TEMP, False)],
        )
        checker.check(
            "恢复正常自动关闭告警",
            any(
                event.get("kind") == "recovered" and event.get("point_key") == "temp_in"
                for event in recovered.get("events", [])
            ),
            f"status={recovered.get('status')}",
        )
        checker.check(
            "活动告警已消失",
            "temp_in_high" not in active_alert_types(api, device),
        )

        opened = post_batch(
            api, token,
            [envelope(device, base_time + timedelta(seconds=50), 6, NORMAL_TEMP, True)],
        )
        checker.check(
            "门磁开门事件",
            any(
                event.get("kind") == "door" and event.get("open") is True
                for event in opened.get("events", [])
            ),
        )
        closed = post_batch(
            api, token,
            [envelope(device, base_time + timedelta(seconds=60), 7, NORMAL_TEMP, False)],
        )
        checker.check(
            "门磁关门事件",
            any(
                event.get("kind") == "door" and event.get("open") is False
                for event in closed.get("events", [])
            ),
        )

        status, snapshot = http_json(api, "GET", f"/api/v1/iot/devices/{device}/state")
        ok = (
            status == 200
            and isinstance(snapshot, dict)
            and snapshot.get("status") == "online"
            and snapshot.get("quality") == "good"
        )
        checker.check(
            "设备面板读模型（status=online, quality=good）",
            ok,
            f"status={snapshot.get('status') if isinstance(snapshot, dict) else status}",
        )
    except FlowError as exc:
        checker.check("遥测闭环执行", False, str(exc))

    return checker.report()


def main() -> int:
    env = read_env()
    parser = argparse.ArgumentParser(description="无硬件虚拟验收")
    parser.add_argument(
        "--api", default=f"http://127.0.0.1:{env.get('HHLG_API_PORT', '8010')}"
    )
    parser.add_argument("--device", default="SIM-ACC-01", help="验收用设备编码")
    parser.add_argument(
        "--device-token", default=env.get("DEVICE_INGEST_TOKEN") or None,
        help="X-Device-Token，默认读 .env 的 DEVICE_INGEST_TOKEN",
    )
    args = parser.parse_args()
    return run(args.api, args.device, args.device_token)


if __name__ == "__main__":
    raise SystemExit(main())
