"""一键起栈到可演示：生成 .env → docker compose 起栈 → 演示账号 → 演示数据 → 冒烟。

用法：
    python scripts/bootstrap.py                 # 带模拟设备（demo profile）
    python scripts/bootstrap.py --no-demo       # 不启动模拟设备
    python scripts/bootstrap.py --skip-build    # 复用已有镜像

幂等：重复执行不会清空已有业务数据；仅当 resources 表为空且库内只有演示供应商时
才导入 backend/scripts/seed_demo.sql（该脚本假定 user_id=1）。
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _flow import (  # noqa: E402
    ENV_PATH,
    EXAMPLE_ENV_PATH,
    ROOT,
    FlowError,
    compose,
    docker_ready,
    http_json,
    lan_ip,
    read_env,
    wait_health,
    write_env,
)

SEED_SQL = ROOT / "backend" / "scripts" / "seed_demo.sql"
DEMO_PASSWORD = "Demo@123456"
ACCOUNTS = [
    # 供应商必须先注册：seed_demo.sql 把资源挂在 user_id=1 上
    ("demo_supplier", "supplier", "怀化冷链仓储有限公司"),
    ("demo_admin", "admin", "平台运营中心"),
]


def ensure_env() -> dict[str, str]:
    """首次运行从模板生成 .env，并补齐空密钥。"""
    if not ENV_PATH.exists():
        if not EXAMPLE_ENV_PATH.exists():
            raise FlowError("缺少 .env.example，无法生成 .env")
        ENV_PATH.write_text(EXAMPLE_ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print("[env] 已从 .env.example 生成 .env")
    env = read_env()
    updates: dict[str, str] = {}
    jwt = env.get("JWT_SECRET", "")
    if not jwt or jwt.startswith("please-change") or jwt.startswith("change-me"):
        updates["JWT_SECRET"] = secrets.token_urlsafe(48)
    if not env.get("DEVICE_INGEST_TOKEN"):
        updates["DEVICE_INGEST_TOKEN"] = secrets.token_hex(16)
    if not env.get("OTA_SIGNING_KEY"):
        # Ed25519 私钥种子（hex），只在本机打包固件时使用，不进容器
        updates["OTA_SIGNING_KEY"] = secrets.token_hex(32)
    if updates:
        write_env(updates)
        print(f"[env] 已写入 {', '.join(updates)}")
        env = read_env()
    return env


def db_scalar(env: dict[str, str], sql: str) -> str:
    """在 mysql 容器里执行单行查询。"""
    root_pw = env.get("MYSQL_ROOT_PASSWORD") or "root123456"
    proc = compose(
        [
            "exec", "-T", "mysql", "mysql", "-N", "-B", "-uroot",
            f"-p{root_pw}", "huaihua_logistics", "-e", sql,
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise FlowError("数据库查询失败：\n" + (proc.stdout or "")[-1500:])
    # docker compose 可能把警告一起打到 stdout，这里只取纯数字结果行
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit() or (line.startswith("-") and line[1:].isdigit()):
            return line
    return ""


def ensure_accounts(api: str) -> str | None:
    """登录或注册演示账号，返回管理员 token。"""
    token: str | None = None
    for username, role, company in ACCOUNTS:
        status, data = http_json(
            api, "POST", "/api/v1/auth/login",
            {"username": username, "password": DEMO_PASSWORD},
        )
        if status == 200 and isinstance(data, dict) and data.get("access_token"):
            print(f"[account] {username} 已存在，直接登录")
        else:
            status, data = http_json(
                api, "POST", "/api/v1/auth/register",
                {
                    "username": username,
                    "password": DEMO_PASSWORD,
                    "role": role,
                    "company_name": company,
                },
            )
            if status in (200, 201):
                print(f"[account] 已创建 {username}（{role}）")
            else:
                detail = data.get("detail") if isinstance(data, dict) else data
                print(f"[account] {username} 创建失败 HTTP {status}：{detail}")
                continue
        status, data = http_json(
            api, "POST", "/api/v1/auth/login",
            {"username": username, "password": DEMO_PASSWORD},
        )
        if status == 200 and isinstance(data, dict):
            if username == "demo_admin":
                token = data.get("access_token")
    return token


def seed_if_empty(env: dict[str, str]) -> None:
    resources = int(db_scalar(env, "SELECT COUNT(*) FROM resources") or 0)
    if resources:
        print(f"[seed] 已有 {resources} 条资源，跳过演示数据导入")
        return
    users = int(db_scalar(env, "SELECT COUNT(*) FROM users") or 0)
    if users == 0:
        print("[seed] 库内没有用户，跳过（请先确认演示账号创建成功）")
        return
    supplier_id = db_scalar(env, "SELECT id FROM users WHERE username='demo_supplier'")
    if supplier_id != "1":
        print(
            "[seed] 跳过：库内已有其他账号，demo_supplier 的 id 不是 1。"
            "seed_demo.sql 会把 36 个冷链箱挂到 user_id=1，为避免数据错挂不自动导入。"
        )
        return
    if not SEED_SQL.exists():
        raise FlowError(f"缺少 {SEED_SQL}")
    root_pw = env.get("MYSQL_ROOT_PASSWORD") or "root123456"
    proc = compose(
        [
            "exec", "-T", "mysql", "mysql", "-uroot", f"-p{root_pw}",
            "--default-character-set=utf8mb4", "huaihua_logistics",
        ],
        stdin_path=SEED_SQL,
        check=False,
    )
    if proc.returncode != 0:
        raise FlowError("演示数据导入失败：\n" + (proc.stdout or "")[-2000:])
    print("[seed] 已导入 36 个冷链箱 / 36 台设备 / 孪生节点与绑定")


def run_smoke(web: str, api: str, demand: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "SMOKE_WEB": web,
            "SMOKE_API": api,
            "SMOKE_DEMAND": demand,
            "SMOKE_USERNAME": "demo_admin",
            "SMOKE_PASSWORD": DEMO_PASSWORD,
        }
    )
    print("\n[smoke] python scripts/smoke.py")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "smoke.py")],
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        raise FlowError(f"冒烟测试未通过（退出码 {proc.returncode}）")


def main() -> int:
    parser = argparse.ArgumentParser(description="一键起栈并准备演示数据")
    parser.add_argument("--no-demo", action="store_true", help="不启动模拟设备（demo profile）")
    parser.add_argument("--skip-build", action="store_true", help="不重新构建镜像")
    parser.add_argument("--no-seed", action="store_true", help="不导入演示数据")
    parser.add_argument("--skip-smoke", action="store_true", help="跳过 HTTP 冒烟")
    parser.add_argument("--timeout", type=float, default=420, help="等待健康检查秒数")
    args = parser.parse_args()

    try:
        env = ensure_env()
        web = f"http://127.0.0.1:{env.get('HHLG_WEB_PORT', '8080')}"
        api = f"http://127.0.0.1:{env.get('HHLG_API_PORT', '8010')}"
        demand = f"http://127.0.0.1:{env.get('HHLG_DEMAND_PORT', '8081')}"

        if not docker_ready():
            raise FlowError(
                "未检测到 docker compose。请先安装并启动 Docker Desktop / Engine，"
                "再执行本脚本；也可以在服务器上用 docker compose up -d --build 手动起栈。"
            )

        up = ["--profile", "demo", "up", "-d"] if not args.no_demo else ["up", "-d"]
        if not args.skip_build:
            up.append("--build")
        print("[stack] docker compose " + " ".join(up))
        compose(up, capture=False)

        print(f"[stack] 等待后端健康检查 {api}/api/health ...")
        wait_health(api, timeout=args.timeout)
        print("[stack] 后端已就绪")

        ensure_accounts(api)
        if args.no_seed:
            print("[seed] 已按参数跳过")
        else:
            seed_if_empty(env)

        if not args.skip_smoke:
            run_smoke(web, api, demand)

        ip = lan_ip()
        emqx_pw = env.get("EMQX_DASH_PASSWORD") or "public123"
        print(
            "\n================ 起栈完成 ================\n"
            f"管理端 / 供应商端 : {web}\n"
            f"需求端 H5         : {demand}\n"
            f"后端 API 文档     : {api}/docs\n"
            f"EMQX 控制台       : http://127.0.0.1:{env.get('HHLG_EMQX_DASH_PORT', '18084')}"
            f"（admin / {emqx_pw}）\n"
            f"设备接入地址      : http://{ip}:{env.get('HHLG_WEB_PORT', '8080')}"
            f"（预配固件时自动写入）\n"
            "演示账号          : demo_admin / Demo@123456（管理员）\n"
            "                    demo_supplier / Demo@123456（供应商）\n"
            "\n下一步            : python scripts/acceptance.py\n"
            "                    python scripts/provision_devices.py\n"
        )
        return 0
    except FlowError as exc:
        print(f"\n[失败] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
