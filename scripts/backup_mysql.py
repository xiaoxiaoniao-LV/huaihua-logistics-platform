#!/usr/bin/env python3
"""MySQL 逻辑备份：docker compose exec mysqldump → gzip → 按保留天数清理。

用法：
    python scripts/backup_mysql.py                 # 备份到 backups/，保留 7 天
    python scripts/backup_mysql.py --keep-days 30
    python scripts/backup_mysql.py --out D:/backup/hlg

密码优先取环境变量 MYSQL_ROOT_PASSWORD，其次取根目录 .env。
仅依赖标准库，Windows / Linux 均可直接执行（需本机可用 docker compose）。
"""
import argparse
import gzip
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = "huaihua_logistics"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def prune(out_dir: Path, keep_days: int) -> list[Path]:
    if keep_days <= 0:
        return []
    cutoff = time.time() - keep_days * 86400
    removed = []
    for path in out_dir.glob("huaihua_logistics_*.sql*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def main() -> int:
    env = load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description="MySQL 逻辑备份")
    parser.add_argument("--out", default=str(ROOT / "backups"), help="备份输出目录")
    parser.add_argument(
        "--keep-days",
        type=int,
        default=int(os.getenv("BACKUP_KEEP_DAYS") or env.get("BACKUP_KEEP_DAYS") or 7),
        help="保留天数，<=0 表示不清理",
    )
    parser.add_argument("--database", default=DEFAULT_DB)
    parser.add_argument("--user", default="root")
    parser.add_argument("--no-compress", action="store_true", help="输出未压缩 .sql")
    args = parser.parse_args()

    password = (
        os.getenv("MYSQL_ROOT_PASSWORD")
        or env.get("MYSQL_ROOT_PASSWORD")
        or "root123456"
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "docker", "compose", "exec", "-T",
        "-e", f"MYSQL_PWD={password}",
        "mysql", "mysqldump",
        "-u", args.user,
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--default-character-set=utf8mb4",
        args.database,
    ]
    print(f"[backup] 执行：{' '.join(cmd[:6])} … {args.database}")
    proc = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
        print("[backup] 失败：mysqldump 返回非零退出码", file=sys.stderr)
        return 1

    data = proc.stdout
    if len(data) < 1024 or b"MySQL dump" not in data[:4096]:
        print("[backup] 失败：导出内容为空或不是合法 SQL 转储", file=sys.stderr)
        return 1

    stamp = time.strftime("%Y%m%d_%H%M%S")
    target = out_dir / f"huaihua_logistics_{stamp}.sql"
    if args.no_compress:
        target.write_bytes(data)
    else:
        target = target.with_suffix(".sql.gz")
        with gzip.open(target, "wb", compresslevel=6) as fh:
            fh.write(data)

    size_mb = target.stat().st_size / 1024 / 1024
    print(f"[backup] 完成：{target}（{size_mb:.2f} MB）")

    for path in prune(out_dir, args.keep_days):
        print(f"[backup] 清理过期备份：{path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
