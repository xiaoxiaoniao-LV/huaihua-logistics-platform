"""HTTP 窄表遥测模拟器：无需 MQTT Broker，直接演练 P0 硬件链路。

覆盖三件事：
1. 常态上报 temp_in / hum_in / door / rssi
2. 门磁开合 → 平台 door_open / door_close 事件
3. 断网补传 → 本地积压后按 seq 顺序批量重放（平台幂等）

用法：
  set DEVICE_TOKEN=<backend/.env 的 DEVICE_INGEST_TOKEN>
  python simulator_http.py                     # 交互模式，默认设备 SIM-HTTP-01
  python simulator_http.py --scenario all      # 自动演练：门磁 + 越限 + 断网补传
  python simulator_http.py --scenario offline  # 只演练断网补传
  python simulator_http.py --device CW-01 --interval 2

交互命令：o 开门 / c 关门 / h 模拟越限 / n 恢复正常 / f 断网补传 / q 退出
环境变量：API_BASE（默认 http://127.0.0.1:8002）、DEVICE_TOKEN、DEVICE_CODE
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8002").rstrip("/")
TOKEN = os.environ.get("DEVICE_TOKEN", "")
FIRMWARE_VERSION = os.environ.get("FIRMWARE_VERSION", "2.0.0-sim")

state = {
    "door": False,
    "over_limit": 0,     # 剩余越限采样数
    "offline": 0,        # 剩余离线（只缓存不发送）采样数
    "running": True,
}
seq = 0
buffer = []              # 模拟板载环形缓存


def log(*args):
    print("[sim-http]", *args, flush=True)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def build_envelope(device):
    global seq
    if state["over_limit"] > 0:
        temp = -2.0
        state["over_limit"] -= 1
        if state["over_limit"] == 0:
            log("越限采样结束，下一采样回到 -18℃")
    else:
        temp = -18.0

    env = {
        "device_code": device,
        "ts": now_iso(),
        "seq": seq,
        "quality": "good",
        "firmware_version": FIRMWARE_VERSION,
        "points": {
            "temp_in": temp,
            "hum_in": 65.0,
            "door": bool(state["door"]),
            "rssi": -62,
        },
    }
    seq += 1
    return env


def post(items):
    """返回 (HTTP 状态码 | None, 响应 JSON | None)。"""
    body = json.dumps({"items": items}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["X-Device-Token"] = TOKEN
    req = urllib.request.Request(
        API_BASE + "/api/v1/iot/telemetry", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        return e.code, {"detail": detail}
    except Exception as e:
        return None, {"detail": str(e)}


def describe(result):
    if not result or "devices" not in result:
        return str(result)
    parts = [f"accepted={result.get('accepted')} duplicates={result.get('duplicates')}"]
    for dev in result["devices"]:
        for event in dev.get("events", []):
            parts.append(f"event={event.get('kind')}:{event.get('message')}")
    return " ".join(parts)


def flush_buffer():
    """补传积压数据：按 seq 顺序，每批 50 条。"""
    if not buffer:
        return True
    log("开始补传", len(buffer), "条积压数据")
    while buffer:
        batch, buffer[:] = buffer[:50], buffer[50:]
        code, result = post(batch)
        if code in (200, 201):
            log("补传成功", len(batch), "条 →", describe(result))
        else:
            log("补传失败，剩余", len(buffer) + len(batch), "条，稍后重试:", result)
            buffer[:0] = batch
            return False
    return True


def step(device):
    env = build_envelope(device)

    if state["offline"] > 0:
        state["offline"] -= 1
        buffer.append(env)
        log(f"断网中，缓存第 {len(buffer)} 条 ts={env['ts']}")
        if state["offline"] == 0:
            log("网络恢复，转入批量补传")
            flush_buffer()
        return

    code, result = post([env])
    if code in (200, 201):
        log(f"{env['ts']} temp={env['points']['temp_in']}℃ door={env['points']['door']} → {describe(result)}")
    else:
        buffer.append(env)
        log(f"上报失败({code})，转入缓存，当前积压 {len(buffer)} 条")


def interactive(device, interval):
    def reader():
        while state["running"]:
            try:
                cmd = input().strip().lower()
            except EOFError:
                break
            if cmd == "o":
                state["door"] = True
                log("门磁 → 开")
            elif cmd == "c":
                state["door"] = False
                log("门磁 → 关")
            elif cmd == "h":
                state["over_limit"] = 4
                log("接下来 4 个采样为 -2℃（高于 -5℃ 上限），第 3 次触发告警")
            elif cmd == "n":
                state["over_limit"] = 0
                log("恢复正常温度 -18℃")
            elif cmd == "f":
                state["offline"] = 5
                log("模拟断网 5 个采样，之后自动补传")
            elif cmd == "q":
                state["running"] = False
                break
            else:
                log("命令：o 开门 / c 关门 / h 越限 / n 恢复 / f 断网 / q 退出")

    threading.Thread(target=reader, daemon=True).start()
    log("交互模式，输入 o/c/h/n/f/q 后回车")
    while state["running"]:
        step(device)
        time.sleep(interval)


def run_scenario(name, device, interval):
    steps = {
        "door": [("normal", 1), ("door_open", 2), ("door_close", 2)],
        "alarm": [("over", 4), ("recover", 2)],
        "offline": [("offline", 5)],
    }
    plan = []
    if name == "all":
        plan = steps["door"] + steps["alarm"] + steps["offline"]
    else:
        plan = steps[name]

    log(f"场景 {name} 开始，设备 {device}")
    for action, times in plan:
        if action == "door_open":
            state["door"] = True
            log("门磁 → 开")
        elif action == "door_close":
            state["door"] = False
            log("门磁 → 关")
        elif action == "over":
            state["over_limit"] = times
            log(f"越限 {times} 个采样")
        elif action == "recover":
            state["over_limit"] = 0
            log("恢复正常温度")
        elif action == "offline":
            state["offline"] = times
            log(f"模拟断网 {times} 个采样后补传")
        for _ in range(times):
            step(device)
            time.sleep(interval)
    log("场景结束")


def main():
    parser = argparse.ArgumentParser(description="HTTP 窄表遥测模拟器")
    parser.add_argument("--device", default=os.environ.get("DEVICE_CODE", "SIM-HTTP-01"))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("INTERVAL", "2")))
    parser.add_argument("--scenario", choices=["all", "door", "alarm", "offline"])
    args = parser.parse_args()

    if not TOKEN:
        log("提示：未设置 DEVICE_TOKEN，后端配置了 DEVICE_INGEST_TOKEN 时会返回 401")
    log(f"API_BASE={API_BASE} device={args.device}")

    if args.scenario:
        run_scenario(args.scenario, args.device, args.interval)
    else:
        interactive(args.device, args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已停止")
        sys.exit(0)
