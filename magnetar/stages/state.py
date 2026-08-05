"""STATE: 轻量结构化任务状态（.magnetar-state.json）。

相比 task.md（人类可读的追加式审计），state 文件只保留：
- 当前阶段与状态（INIT/ACQUIRE/EXPORT/.../PUBLISH）
- 关键产物路径
- 一句话摘要与关键指标

Agent 的进度判断、断点续跑、阶段汇报都应优先读取本文件，避免全量读 task.md /
analysis.md / 各阶段报告。所有 stage 函数收尾时自动调用 ``mark_stage``。
"""
import json
from datetime import datetime
from pathlib import Path


STATE_NAME = ".magnetar-state.json"


def load(task_dir: Path | str) -> dict:
    """读取任务状态；文件不存在或损坏时返回空初始状态。"""
    p = Path(task_dir) / STATE_NAME
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"stage": "INIT", "status": "running", "artifacts": {}, "metrics": {}, "summary": ""}


def save(task_dir: Path | str, **updates) -> dict:
    """更新并写回状态文件，返回最新状态。"""
    task_dir = Path(task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)
    state = load(task_dir)
    state.update(updates)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (task_dir / STATE_NAME).write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return state


def mark_stage(task_dir: Path | str, stage: str, status: str = "done",
               artifacts: dict | None = None, metrics: dict | None = None,
               summary: str = "") -> dict:
    """标记阶段完成并合并产物/指标；summary 只放一句话，详细内容落盘到对应报告。"""
    task_dir = Path(task_dir)
    current = load(task_dir)
    updates: dict = {"stage": stage, "status": status}
    if artifacts:
        merged = dict(current.get("artifacts", {}))
        merged.update(artifacts)
        updates["artifacts"] = merged
    if metrics:
        merged = dict(current.get("metrics", {}))
        merged.update(metrics)
        updates["metrics"] = merged
    if summary:
        updates["summary"] = summary
    return save(task_dir, **updates)
