"""PACKAGE: 组装客户交付包。"""
import json, os, shutil, textwrap
from pathlib import Path

def assemble(task_dir: Path, metrics: dict, pulsar_image: str, model_name="mobilenet_v2", labels=None) -> Path:
    pkg = task_dir / "package"; pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "models").mkdir(exist_ok=True)
    shutil.copy2(task_dir / "compile" / "model.axmodel", pkg / "models" / "model.axmodel")
    shutil.copy2(task_dir / "export" / "model_meta.json", pkg / "models" / "model_meta.json")
    py_src = task_dir / "sdk" / "python"
    if py_src.exists(): shutil.copytree(py_src, pkg / "python", dirs_exist_ok=True)
    cpp_src = task_dir / "sdk" / "cpp"
    if cpp_src.exists(): shutil.copytree(cpp_src, pkg / "cpp", dirs_exist_ok=True)
    mc = pkg / "model_convert"; mc.mkdir(exist_ok=True)
    shutil.copy2(task_dir / "compile" / "pulsar2_config.json", mc / "pulsar2_config.json")
    shutil.copy2(task_dir / "export" / "model_meta.json", mc / "model_meta.json")
    (mc / "compile_pulsar2.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\npulsar2 build --config pulsar2_config.json\n", encoding="utf-8")
    os.chmod(mc / "compile_pulsar2.sh", 0o755)
    (mc / "README.md").write_text(f"# Model Convert\n\nOriginal compile used Docker image `{pulsar_image}`.\n", encoding="utf-8")
    reports = pkg / "reports"; reports.mkdir(exist_ok=True)
    for rn in ["export_report.md", "compile_report.md", "simulate_report.md"]:
        src = task_dir / ("export" if "export" in rn else "compile" if "compile" in rn else "simulate") / rn
        if src.exists(): shutil.copy2(src, reports / rn)
    rb = task_dir / "runonboard" / "runonboard_report.md"
    if rb.exists(): shutil.copy2(rb, reports / "runonboard_report.md")
    cos = metrics.get("cosine_similarity", "N/A")
    (pkg / "README.md").write_text(textwrap.dedent(f"""\
        # {model_name} AXMODEL Project
        - cosine_similarity: {cos}
        ## Layout
        - `models/`: AXMODEL + metadata
        - `python/`: Python SDK (pyaxengine)
        - `cpp/`: C++ SDK (AX Engine runtime)
        - `model_convert/`: export + compile scripts
        - `reports/`: stage reports
    """), encoding="utf-8")
    (pkg / ".gitignore").write_text("__pycache__/\n*.pyc\nbuild/\nCMakeFiles/\nCMakeCache.txt\n", encoding="utf-8")
    return pkg
