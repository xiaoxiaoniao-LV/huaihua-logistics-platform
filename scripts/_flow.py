"""自动化脚本共用的小工具（仅标准库）。

被 bootstrap.py / acceptance.py / provision_devices.py 复用：
- 读取根目录 .env（叠加 .env.example 默认值与进程环境变量）
- 生成/更新 .env 中的密钥项
- JSON HTTP 调用（带 Bearer / X-Device-Token）
- docker compose 子进程封装
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE_ENV_PATH = ROOT / ".env.example"

DEFAULT_PORTS = {
    "HHLG_WEB_PORT": "8080",
    "HHLG_API_PORT": "8010",
    "HHLG_DEMAND_PORT": "8081",
    "HHLG_MQTT_PORT": "1884",
    "HHLG_EMQX_DASH_PORT": "18084",
}


class FlowError(RuntimeError):
    """自动化流程中的可预期失败（打印后退出，不抛栈）。"""


def read_env() -> dict[str, str]:
    """.env.example 打底 → .env 覆盖 → 同名进程环境变量覆盖。"""
    values = dict(DEFAULT_PORTS)
    for path in (EXAMPLE_ENV_PATH, ENV_PATH):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in list(values):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def write_env(updates: dict[str, str]) -> None:
    """就地更新 .env 的指定键；文件中没有的键追加到末尾。"""
    base = ENV_PATH if ENV_PATH.exists() else EXAMPLE_ENV_PATH
    if not base.exists():
        raise FlowError("缺少 .env 与 .env.example，无法写入配置")
    lines = base.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    missing = [f"{key}={value}" for key, value in updates.items() if key not in seen]
    if missing:
        out.extend(["", "# 由自动化脚本生成（本地密钥，不要提交）", *missing])
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def http_json(
    base: str,
    method: str,
    path: str,
    payload: dict | list | None = None,
    token: str | None = None,
    device_token: str | None = None,
    timeout: float = 15,
) -> tuple[int, object]:
    """返回 (status_code, body)。HTTP 4xx/5xx 不抛异常，连接失败抛 FlowError。"""
    url = base.rstrip("/") + path
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if device_token:
        headers["X-Device-Token"] = device_token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"detail": raw[:500]}
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FlowError(f"{method} {url} 不可达：{exc}") from exc


def wait_health(base: str, timeout: float = 420, interval: float = 3) -> dict:
    """轮询 /api/health 直到 200 且 status=ok。"""
    deadline = time.time() + timeout
    last = "尚未响应"
    while time.time() < deadline:
        try:
            status, payload = http_json(base, "GET", "/api/health", timeout=5)
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return payload
            last = f"HTTP {status}"
        except FlowError as exc:
            last = str(exc)
        time.sleep(interval)
    raise FlowError(f"等待 {base}/api/health 超时（{int(timeout)}s，最后状态：{last}）")


def docker_ready() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def compose(
    args: list[str],
    stdin_path: Path | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """执行 docker compose <args>，stdin 可重定向到 SQL 文件。"""
    stdin = None
    try:
        if stdin_path is not None:
            stdin = open(stdin_path, "r", encoding="utf-8")
        proc = subprocess.run(
            ["docker", "compose", *args],
            cwd=str(ROOT),
            stdin=stdin if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise FlowError(f"无法执行 docker compose：{exc}") from exc
    finally:
        if stdin is not None:
            stdin.close()
    if check and proc.returncode != 0:
        tail = (proc.stdout or "")[-2000:]
        raise FlowError(f"docker compose {' '.join(args)} 失败：\n{tail}")
    return proc


def lan_ip() -> str:
    """取本机对外的局域网地址（设备要从这一地址访问平台）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def api_base(env: dict[str, str]) -> str:
    return f"http://127.0.0.1:{env.get('HHLG_API_PORT', '8010')}"


def web_base(env: dict[str, str]) -> str:
    return f"http://127.0.0.1:{env.get('HHLG_WEB_PORT', '8080')}"
