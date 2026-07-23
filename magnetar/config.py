"""读取 .magnetarrc 配置和环境变量。"""
import os, re
from pathlib import Path

def load_config(project_root: Path | None = None) -> dict:
    if project_root is None:
        for parent in [Path.cwd(), *Path.cwd().parents]:
            if (parent / ".magnetarrc").exists() or (parent / ".git").exists():
                project_root = parent; break
        else:
            project_root = Path.cwd()
    cfg: dict[str, str] = {}
    rc = project_root / ".magnetarrc"
    if rc.exists():
        for line in rc.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            m = re.match(r"^(\w+)\s*=\s*(.*)", line)
            if m: cfg[m.group(1)] = m.group(2).strip()
    for key in cfg:
        if os.environ.get(key): cfg[key] = os.environ[key]
    cfg.setdefault("TARGET_HARDWARE", "AX650")
    cfg.setdefault("SDK_LANG", "both")
    cfg.setdefault("BOARD_PASSWORD", os.environ.get("MAGNETAR_BOARD_PASSWORD", "123456"))
    return cfg
