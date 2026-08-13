"""SCRATCH: 本机任务临时文件管理。

约定：所有运行时临时目录一律放 ``TASK_DIR/cache/scratch/<用途>/``（任务自有、
随任务走），不再散落 /tmp。任务收尾调 ``cleanup_scratch()`` 清理；新任务开始前
用 ``local_stale_report()`` 检查历史遗留（老版本 /tmp/magnetar_* 残留与已完成
任务的 scratch），明确哪些可以安全清理。
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

SCRATCH_SUBDIR = Path("cache") / "scratch"
# 老版本 /tmp 残留目录前缀（历史 self_test / HF 发布遗留，可安全清理）
STALE_PREFIXES = ("magnetar_pkg_test_", "magnetar_hf_")
DEFAULT_TASK_ROOT = Path("todos") / "work"


def scratch_dir(task_dir: Path | str, name: str) -> Path:
    """返回任务 scratch 子目录（TASK_DIR/cache/scratch/<name>），自动创建。

    name 支持 "用途/子目录" 嵌套；每段做安全化（非法字符替换为 _）。
    """
    safe = "/".join(re.sub(r"[^0-9A-Za-z_.-]", "_", seg) for seg in str(name).split("/"))
    d = Path(task_dir) / SCRATCH_SUBDIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup_scratch(task_dir: Path | str, *, keep: set[str] | None = None) -> list[str]:
    """清空任务 scratch 下除 keep 外的所有子目录；返回已删除路径。"""
    root = Path(task_dir) / SCRATCH_SUBDIR
    if not root.is_dir():
        return []
    keep = keep or set()
    removed: list[str] = []
    for child in sorted(root.iterdir()):
        if child.name in keep:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed.append(str(child))
    return removed


def _dir_size_mb(path: Path) -> float:
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    except OSError:
        pass
    return total / (1024 * 1024)


def _age_minutes(path: Path) -> int:
    try:
        return max(0, int((datetime.now().timestamp() - path.stat().st_mtime) // 60))
    except OSError:
        return -1


def _task_status(task_dir: Path) -> str:
    state = task_dir / ".magnetar-state.json"
    try:
        return json.loads(state.read_text(encoding="utf-8")).get("status", "unknown")
    except Exception:
        return "unknown"


def local_stale_report(*, tmp_root: Path | str | None = None,
                       task_root: Path | str | None = None) -> list[dict]:
    """扫描可安全清理的历史临时残留（只读，不删除）。

    - ``tmp_root``（默认 $TMPDIR 或 /tmp）下本工作流前缀的遗留目录；
    - ``task_root``（默认 todos/work）下已完成/失败任务的 cache/scratch
      （状态为 running 的任务不列入，避免误清活任务）。
    返回按新旧排序的 [{path, kind, age_min, size_mb, reason}]。
    """
    tmp_root = Path(tmp_root or os.environ.get("TMPDIR") or "/tmp")
    task_root = Path(task_root or Path.cwd() / DEFAULT_TASK_ROOT)
    stale: list[dict] = []

    if tmp_root.is_dir():
        for child in sorted(tmp_root.iterdir(), key=lambda p: p.stat().st_mtime):
            if not child.is_dir() or not child.name.startswith(STALE_PREFIXES):
                continue
            stale.append({
                "path": str(child),
                "kind": "legacy-tmp",
                "age_min": _age_minutes(child),
                "size_mb": _dir_size_mb(child),
                "reason": "老版本 /tmp 遗留（临时目录，可清理）",
            })

    if task_root.is_dir():
        for task_dir in sorted(task_root.iterdir()):
            if not task_dir.is_dir():
                continue
            status = _task_status(task_dir)
            if status == "running":
                continue  # 活任务不列入
            scratch = task_dir / SCRATCH_SUBDIR
            if not scratch.is_dir():
                continue
            size = _dir_size_mb(scratch)
            stale.append({
                "path": str(scratch),
                "kind": "task-scratch",
                "age_min": _age_minutes(scratch),
                "size_mb": size,
                "reason": f"任务已结束（status={status or 'unknown'}），scratch 可清理",
            })

    stale.sort(key=lambda d: d["age_min"], reverse=True)
    return stale


def remove_paths(paths: list[str | Path]) -> list[str]:
    """按显式路径删除（目录递归/文件），容忍缺失；返回实际删除的路径。"""
    removed: list[str] = []
    for p in paths:
        p = Path(p)
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
            removed.append(str(p))
        except OSError:
            pass
    return removed
