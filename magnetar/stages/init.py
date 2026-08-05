"""INIT: 创建隔离任务工作目录。"""
import json, textwrap
from datetime import datetime
from pathlib import Path

def run(config: dict) -> Path:
    task_dir_str = config.get("TASK_DIR") or ""
    task_dir = Path(task_dir_str)
    if not task_dir_str:
        mn = config.get("MODEL_NAME") or "model"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_dir = Path.cwd() / "todos" / "work" / f"{ts}-{mn}"
    for d in ["origin", "export", "compile", "simulate", "sdk/python", "sdk/cpp", "runonboard", "package", "cache"]:
        (task_dir / d).mkdir(parents=True, exist_ok=True)
    from magnetar.stages.state import mark_stage
    mark_stage(
        task_dir, "INIT",
        artifacts={"task_dir": str(task_dir), "config": str(task_dir / "config.json")},
        summary=f"模型 {config.get('MODEL_NAME', 'N/A')} → {config.get('TARGET_HARDWARE', 'AX650')}",
    )
    (task_dir / "task.md").write_text(textwrap.dedent(f"""\
        # {config.get('MODEL_NAME', 'Model')} Deployment
        - SOURCE: {config.get('SOURCE', 'N/A')}
        - TARGET_HARDWARE: {config['TARGET_HARDWARE']}
        - STATUS: INIT
        """), encoding="utf-8")
    (task_dir / "analysis.md").write_text(f"Magnetar pipeline started at {datetime.now().isoformat()}\n", encoding="utf-8")
    (task_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return task_dir
