#!/usr/bin/env python3
"""静态检查：源码中只允许 /api/health 与 /api/v1/* 两类接口前缀。

防止 API 前缀再次分裂（历史上出现过 /api/orders 与 /api/v1/orders 并存）。
扫描 backend/app、frontend-vue/src、demand-app/src，忽略文档与构建产物。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "backend" / "app",
    ROOT / "frontend-vue" / "src",
    ROOT / "demand-app" / "src",
]
SUFFIXES = {".py", ".ts", ".vue", ".js"}
# 匹配 "/api/" 后不是 v1/ 或 health 的情况
BAD_PREFIX = re.compile(r"""['"`]/api/(?!v1/|health)""")
SKIP_PARTS = {"node_modules", "dist", "__pycache__", ".vite"}


def iter_files(base: Path):
    if not base.exists():
        return
    for path in base.rglob("*"):
        if path.is_file() and path.suffix in SUFFIXES and not (SKIP_PARTS & set(path.parts)):
            yield path


def main() -> int:
    problems: list[str] = []
    for base in TARGETS:
        for path in iter_files(base):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if BAD_PREFIX.search(line):
                    rel = path.relative_to(ROOT)
                    problems.append(f"{rel}:{lineno}: {line.strip()}")

    if problems:
        print("发现未统一到 /api/v1 的接口前缀：")
        for item in problems:
            print("  " + item)
        return 1
    print("API 前缀检查通过：仅存在 /api/v1/* 与 /api/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
