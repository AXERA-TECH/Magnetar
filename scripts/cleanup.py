#!/usr/bin/env python3
"""Magnetar 残留检查/清理：历史 /tmp 遗留、已完成任务 scratch、板端过期租约。

用法:
  python3 scripts/cleanup.py                      # 只读报告（默认）
  python3 scripts/cleanup.py --force              # 清理可安全删除项
  python3 scripts/cleanup.py --board root@10.0.0.1  # 指定板子（覆盖 .magnetarrc BOARD）

设计原则：默认只报告"该不该清"，--force 才动文件；板端只清 mtime 超过 TTL 的
过期租约，活租约（心跳新鲜）绝不碰。
"""
import argparse
import sys
import urllib.parse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="清理可安全删除项（默认只报告）")
    ap.add_argument("--board", default="",
                    help="板子 user@host[:port]，覆盖 .magnetarrc 的 BOARD")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from magnetar.config import load_config
    from magnetar.scratch import local_stale_report, remove_paths

    cfg = load_config(repo)

    print("=== 本机残留 ===")
    stale = local_stale_report()
    if not stale:
        print("  无历史临时残留（干净）")
    for item in stale:
        age = item["age_min"]
        age_s = f"{age}min" if age >= 0 else "?"
        print(f"  [{item['kind']}] {age_s:>10}  {item['size_mb']:8.1f}MB  "
              f"{item['path']}\n      {item['reason']}")
    if args.force and stale:
        removed = remove_paths([i["path"] for i in stale])
        print(f"  已清理 {len(removed)} 项")

    print()
    print("=== 板端租约 ===")
    board_spec = args.board or cfg.get("BOARD") or ""
    if not board_spec:
        print("  未配置 BOARD，跳过（可用 --board root@host[:port] 指定）")
        return 0
    from magnetar.board_util import (
        BOARD_LEASE_ROOT,
        DEFAULT_LEASE_TTL,
        board_lease_report,
        cleanup_expired_leases,
    )

    p = urllib.parse.urlparse(board_spec if "://" in board_spec
                              else f"ssh://{board_spec}")
    board = {
        "user": p.username or "root",
        "host": p.hostname,
        "port": p.port or 22,
        "password": cfg.get("BOARD_PASSWORD") or "123456",
    }
    if not board["host"]:
        print(f"  无效 BOARD: {board_spec}")
        return 2
    try:
        ttl_min = max(1, DEFAULT_LEASE_TTL // 60)
        report = board_lease_report(board, ttl_min=ttl_min)
    except Exception as e:
        print(f"  板端检查失败: {e}")
        return 1
    if not report:
        print(f"  {BOARD_LEASE_ROOT} 无租约（干净）")
    for item in report:
        age = item["age_min"]
        age_s = f"{age}min" if age is not None else "?"
        flag = "过期" if item["expired"] else "存活"
        print(f"  [{flag}] {age_s:>10}  owner={item['owner']}  "
              f"note={item['note'] or '-'}  token={item['token']}")
    if args.force:
        cleanup_expired_leases(board, ttl_min)
        print(f"  已清理板端 mtime 超过 {ttl_min}min 的过期租约")
    return 0


if __name__ == "__main__":
    sys.exit(main())
