"""INIT: 创建隔离任务工作目录。"""
import json
import textwrap
from datetime import datetime
from pathlib import Path


def run(config: dict) -> Path:
    """创建 TASK_DIR 并初始化 task.md / analysis.md。返回任务目录路径。"""
    task_dir = config.get("TASK_DIR") or ""
    if task_dir:
        task_dir = Path(task_dir)
    else:
        model_name = config.get("MODEL_NAME") or "model"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_dir = Path.cwd() / "todos" / "work" / f"{ts}-{model_name}"

    dirs = [
        "origin", "export", "compile", "simulate",
        "sdk/python", "sdk/cpp", "runonboard", "package", "cache",
    ]
    for d in dirs:
        (task_dir / d).mkdir(parents=True, exist_ok=True)

    (task_dir / "task.md").write_text(textwrap.dedent(f"""\
        # {config.get('MODEL_NAME', 'Model')} Deployment

        - SOURCE: {config.get('SOURCE', 'N/A')}
        - TARGET_HARDWARE: {config['TARGET_HARDWARE']}
        - STATUS: INIT
        """), encoding="utf-8")

    (task_dir / "analysis.md").write_text(
        f"Magnetar pipeline started at {datetime.now().isoformat()}\n", encoding="utf-8")

    (task_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    return task_dir
