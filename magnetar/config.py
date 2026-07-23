"""读取 .magnetarrc 配置和环境变量。"""
import os
import re
from pathlib import Path


def _find_repo_root() -> Path:
    """从当前目录向上查找包含 .magnetarrc 或 .git 的仓库根目录。"""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".magnetarrc").exists() or (parent / ".git").exists():
            return parent
    return cwd


def load_config(project_root: Path | None = None) -> dict:
    """加载配置，优先级：环境变量 > .magnetarrc > 默认值。"""
    if project_root is None:
        project_root = _find_repo_root()
    cfg: dict[str, str] = {}

    # 读取 .magnetarrc
    rc_path = project_root / ".magnetarrc"
    if rc_path.exists():
        for line in rc_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(\w+)\s*=\s*(.*)", line)
            if m:
                cfg[m.group(1)] = m.group(2).strip()

    # 环境变量覆盖
    for key in cfg:
        env_val = os.environ.get(key)
        if env_val is not None:
            cfg[key] = env_val

    # 默认值
    cfg.setdefault("TARGET_HARDWARE", "AX650")
    cfg.setdefault("SDK_LANG", "both")
    cfg.setdefault("BOARD_PASSWORD", os.environ.get("MAGNETAR_BOARD_PASSWORD", "123456"))
    cfg.setdefault("MODE", "full")
    cfg.setdefault("AUTO_APPROVE", "false")

    return cfg
