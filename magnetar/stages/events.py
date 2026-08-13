"""EVENTS: 每任务 append-only 结构化事件日志（TASK_DIR/.magnetar-events.jsonl）。

与 .magnetar-state.json（只保留最新状态）互补：事件日志是可回放的审计流，
阶段完成、产物、指标、错误都按行追加一条 JSON 记录；进程重启可续写。
``state.mark_stage`` 自动写入 stage / artifact / metric 事件，业务代码如需
记录错误或 gate 判定，直接调 ``log_error`` / ``log_event``。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

EVENT_LOG_NAME = ".magnetar-events.jsonl"

_EVENT_TYPES = frozenset({
    "task/start",
    "stage/start",
    "stage/done",
    "stage/skipped",
    "stage/blocked",
    "artifact/created",
    "metric/recorded",
    "error/raised",
    "gate/pass",
    "gate/fail",
    "stop/required",
})


def log_event(task_dir: Path | str, type_: str, *, stage: str | None = None,
              status: str | None = None, **payload) -> dict:
    """追加一条事件并返回写出的记录。type_ 必须在 _EVENT_TYPES 内（fail loud）。"""
    if type_ not in _EVENT_TYPES:
        raise ValueError(f"未知事件类型 {type_!r}，可选: {sorted(_EVENT_TYPES)}")
    task_dir = Path(task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)
    record: dict = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "type": type_,
    }
    if stage:
        record["stage"] = stage
    if status:
        record["status"] = status
    record.update(payload)
    with (task_dir / EVENT_LOG_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def log_error(task_dir: Path | str, exc: BaseException, *,
              stage: str | None = None, code: str | None = None) -> str | None:
    """记录 error/raised；code 优先显式传入，否则用 classify_error 自动提取。"""
    from magnetar.errors import classify_error

    err_code = code or classify_error(exc)
    first_line = (str(exc).strip().splitlines() or [""])[0][:500]
    log_event(task_dir, "error/raised", stage=stage, code=err_code, message=first_line)
    return err_code
