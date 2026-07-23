"""ACQUIRE: 获取模型权重到本地。"""
import shutil
from pathlib import Path

def run(task_dir: Path, source: str) -> Path:
    origin = task_dir / "origin"; origin.mkdir(parents=True, exist_ok=True)
    sp = Path(source).expanduser().resolve()
    if sp.exists():
        if sp.is_dir(): shutil.copytree(sp, origin / sp.name, dirs_exist_ok=True)
        else: shutil.copy2(sp, origin / sp.name)
        detail = f"Local: {sp}"
    else:
        (origin / "source.txt").write_text(source, encoding="utf-8")
        detail = f"Remote: {source}"
    (origin / "ACQUIRE_REPORT.md").write_text(f"# ACQUIRE Report\n\n- Source: {detail}\n", encoding="utf-8")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f: f.write(f"\n- ACQUIRE: {detail}\n")
    return origin
