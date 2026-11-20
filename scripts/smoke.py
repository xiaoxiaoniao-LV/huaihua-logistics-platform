#!/usr/bin/env python3
"""部署冒烟：校验前端页面、健康检查、鉴权登录与核心接口可用。

用法：
    python scripts/smoke.py
    python scripts/smoke.py --web http://127.0.0.1:8080 --api http://127.0.0.1:8010

登录用例可选：设置 SMOKE_USERNAME / SMOKE_PASSWORD 后才会执行，
未设置时跳过（返回码仍为 0，便于 CI 在无种子数据时使用）。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

TIMEOUT = 10


def request(url: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.status, resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="部署冒烟检查")
    parser.add_argument("--web", default=os.getenv("SMOKE_WEB", "http://127.0.0.1:8080"))
    parser.add_argument("--demand", default=os.getenv("SMOKE_DEMAND", "http://127.0.0.1:8081"))
    parser.add_argument("--api", default=os.getenv("SMOKE_API", "http://127.0.0.1:8010"))
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

    # 1. 管理端页面与数字孪生大屏
    for name, path in (("管理端首页", "/"), ("数字孪生大屏", "/screen.html")):
        try:
            status, _ = request(args.web.rstrip("/") + path)
            record(name, status == 200, f"HTTP {status}")
        except Exception as exc:
            record(name, False, str(exc))

    # 2. 需求端 H5
    try:
        status, _ = request(args.demand.rstrip("/") + "/")
        record("需求端首页", status == 200, f"HTTP {status}")
    except Exception as exc:
        record("需求端首页", False, str(exc))

    # 3. 后端健康检查（经 nginx 与直连各一次）
    for name, base in (("健康检查（nginx）", args.web), ("健康检查（直连）", args.api)):
        try:
            status, raw = request(base.rstrip("/") + "/api/health")
            payload = json.loads(raw)
            ok = status == 200 and payload.get("status") == "ok"
            record(name, ok, f"redis={payload.get('redis')} mqtt={payload.get('mqtt')}")
        except Exception as exc:
            record(name, False, str(exc))

    # 4. Prometheus 指标
    try:
        status, raw = request(args.api.rstrip("/") + "/metrics")
        text = raw.decode("utf-8", "ignore")
        ok = status == 200 and "hhlg_http_requests_total" in text
        record("Prometheus 指标", ok, "含 hhlg_http_requests_total" if ok else "缺少指标")
    except urllib.error.HTTPError as exc:
        record("Prometheus 指标", exc.code == 401, f"HTTP {exc.code}（已配置令牌时属正常）")
    except Exception as exc:
        record("Prometheus 指标", False, str(exc))

    # 5. 登录 + 核心接口（需提供账号）
    username = os.getenv("SMOKE_USERNAME")
    password = os.getenv("SMOKE_PASSWORD")
    if username and password:
        try:
            status, raw = request(
                args.api.rstrip("/") + "/api/v1/auth/login",
                method="POST",
                body={"username": username, "password": password},
            )
            token = json.loads(raw).get("access_token")
            record("登录", status == 200 and bool(token), f"HTTP {status}")
            if token:
                status, _ = request(
                    args.api.rstrip("/") + "/api/v1/resources?page=1&size=5", token=token
                )
                record("资源列表", status == 200, f"HTTP {status}")
        except Exception as exc:
            record("登录", False, str(exc))
    else:
        print("[SKIP] 登录与资源列表（未设置 SMOKE_USERNAME / SMOKE_PASSWORD）")

    failed = [name for name, ok, _ in checks if not ok]
    print(f"\n共 {len(checks)} 项，失败 {len(failed)} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
