"""TOOLCHAIN: 验证 Pulsar2 后端（独立包优先/docker 兜底）+ 准备公共 BSP/交叉工具链。"""
import json
from pathlib import Path


def run(cfg: dict | None = None, task_dir: str | Path | None = None) -> str:
    from magnetar.docker_util import extract_pulsar2_proto, parse_backend, resolve_backend
    backend = resolve_backend(cfg)
    kind, name = parse_backend(backend)
    print(f"[TOOLCHAIN] Pulsar2 backend: {kind} ({name})")
    files = extract_pulsar2_proto(backend)
    print("[TOOLCHAIN] proto 已提取到本地缓存:")
    for name, path in files.items():
        print(f"  {name}: {path}")

    # 公共 BSP：AX650 / AX630C / AX620Q（AX620E NPU），地址按芯片来自 build_common.sh
    bsp_info = None
    from magnetar.bsp_util import ensure_bsp
    bsp_info = ensure_bsp((cfg or {}).get("TARGET_HARDWARE", "AX650"), cfg)
    if bsp_info:
        print(f"[TOOLCHAIN] BSP runtime: {bsp_info.get('runtime_root')}")
        print(f"[TOOLCHAIN] BSP 交叉编译器: {bsp_info.get('cross_compiler') or '未找到（C++ 编译将降级）'}")
    if task_dir:
        td = Path(task_dir)
        cfg_path = td / "config.json"
        task_cfg = {}
        if cfg_path.is_file():
            try:
                task_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                task_cfg = {}
        if bsp_info:
            task_cfg["BSP_ROOT"] = bsp_info.get("bsp_dir")
            task_cfg["AX_RUNTIME_ROOT"] = bsp_info.get("runtime_root")
            task_cfg["CXX_TOOLCHAIN"] = bsp_info.get("cross_compiler")
        else:
            task_cfg["BSP_ROOT"] = ""
            task_cfg["AX_RUNTIME_ROOT"] = ""
            task_cfg["CXX_TOOLCHAIN"] = ""
        cfg_path.write_text(json.dumps(task_cfg, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    return backend
