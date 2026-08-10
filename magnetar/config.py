"""读取 .magnetarrc 配置和环境变量。"""
import json, os, re
from pathlib import Path

# 国内镜像默认（环境变量或 .magnetarrc 置空字符串即禁用，海外用户可恢复直连）
MIRROR_DEFAULTS = {
    "HF_ENDPOINT": "https://hf-mirror.com",
    "GH_PROXY": "https://gh-proxy.com",
    "PIP_INDEX_URL": "https://mirrors.aliyun.com/pypi/simple/",
}


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
    for key, default in MIRROR_DEFAULTS.items():
        if os.environ.get(key):
            cfg[key] = os.environ[key]
        cfg.setdefault(key, default)
    return cfg


def load_task_config(task_dir: Path | str, project_root: Path | None = None) -> dict:
    """加载单任务配置：TASK_DIR/config.json（INIT 快照）优先，缺失键回退 .magnetarrc 公共默认，环境变量最后覆盖。

    并发任务隔离约定：每个任务 INIT 时把任务参数（SOURCE/TARGET_HARDWARE/MODEL_NAME/BOARD/TASK_DIR）
    固化到自己的 config.json；之后各阶段一律读本函数，不再回改全局 .magnetarrc。
    """
    cfg = dict(load_config(project_root))
    snap = Path(task_dir) / "config.json"
    if snap.is_file():
        try:
            snap_cfg = json.loads(snap.read_text(encoding="utf-8"))
        except Exception:
            snap_cfg = {}
        cfg.update({k: v for k, v in snap_cfg.items() if v not in (None, "")})
    for key in list(cfg):
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    cfg.setdefault("TASK_DIR", str(task_dir))
    cfg.setdefault("TARGET_HARDWARE", "AX650")
    cfg.setdefault("BOARD_PASSWORD", os.environ.get("MAGNETAR_BOARD_PASSWORD", "123456"))
    for key, default in MIRROR_DEFAULTS.items():
        if os.environ.get(key):
            cfg[key] = os.environ[key]
        cfg.setdefault(key, default)
    return cfg
