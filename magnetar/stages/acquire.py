"""ACQUIRE: 获取模型权重到本地。"""
import shutil
from pathlib import Path


def run(task_dir: Path, source: str) -> Path:
    """下载或复制模型源到 TASK_DIR/origin/。返回源目录路径。"""
    origin = task_dir / "origin"
    origin.mkdir(parents=True, exist_ok=True)

    # 本地路径：直接复制
    source_path = Path(source).expanduser().resolve()
    if source_path.exists():
        if source_path.is_dir():
            shutil.copytree(source_path, origin / source_path.name, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, origin / source_path.name)
        _write_acquire_report(task_dir, f"Local: {source_path}")
        return origin

    # URL/Git/HuggingFace: 记录来源信息，实际下载由 export 阶段按需执行
    (origin / "source.txt").write_text(source, encoding="utf-8")
    _write_acquire_report(task_dir, f"Remote: {source}")
    return origin


def _write_acquire_report(task_dir: Path, detail: str) -> None:
    (task_dir / "origin" / "ACQUIRE_REPORT.md").write_text(
        f"# ACQUIRE Report\n\n- Source: {detail}\n", encoding="utf-8")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"\n- ACQUIRE: {detail}\n")
