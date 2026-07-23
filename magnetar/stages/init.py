"""INIT: 创建隔离任务工作目录。"""
import json, textwrap
from datetime import datetime
from pathlib import Path

def run(config: dict) -> Path:
    task_dir = Path(config.get("TASK_DIR") or "")
    if not str(task_dir):
        mn = config.get("MODEL_NAME") or "model"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_dir = Path.cwd() / "todos" / "work" / f"{ts}-{mn}"
    for d in ["origin", "export", "compile", "simulate", "sdk/python", "sdk/cpp", "runonboard", "package", "cache"]:
        (task_dir / d).mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(textwrap.dedent(f"""\
        # {config.get('MODEL_NAME', 'Model')} Deployment
        - SOURCE: {config.get('SOURCE', 'N/A')}
        - TARGET_HARDWARE: {config['TARGET_HARDWARE']}
        - STATUS: INIT
        """), encoding="utf-8")
    (task_dir / "analysis.md").write_text(f"Magnetar pipeline started at {datetime.now().isoformat()}\n", encoding="utf-8")
    (task_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return task_dir
