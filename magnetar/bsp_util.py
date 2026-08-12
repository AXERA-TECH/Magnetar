"""BSP / 交叉工具链公共目录管理。

痛点：C++ SDK 编译总报找不到 ax_engine 头文件/库——BSP 需要人肉下载，
``AX_RUNTIME_ROOT`` 没有来源。方案：

- BSP 统一放共享目录（``MAGNETAR_BSP_HOME``，默认 ``~/.cache/magnetar/bsp``），
  与 Pulsar2 独立包、base venv 同一套约定，多任务共享、只下载一次；
- ``ensure_bsp()`` 自动下载（ModelScope 优先）/解压/探测 runtime root 与交叉编译器；
- ``build_cpp_sdk()`` 用探测到的 runtime root + 交叉编译器一键 CMake 编译 C++ SDK。

AX650 BSP SDK（V3.10.2，含 include/lib + Neutron 交叉工具链）：
ModelScope ``AXERA-TECH/AX650-Community-Hub``（``CXX_BSP_URL`` 可覆盖）。
AX620E：仅 ``CXX_BSP_URL`` 或本地已有缓存时可用，否则 C++ 编译降级跳过。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from magnetar.net_util import modelscope_url

AX650_REPO = "AXERA-TECH/AX650-Community-Hub"
AX650_SDK_TGZ = "AX650_SDK_V3.10.2_20260513151335.tgz"
AX650_SDK_SUBDIR = "sdk/edge-computing-AX650_SDK_V3.10.2/02. SDK/AX650_SDK_V3.10.2"
AX650_SDK_PKG_DIR = "AX650_SDK_V3.10.2_20260513151335"
ARM_GCC_9_2_URL = ("https://developer.arm.com/-/media/Files/downloads/gnu-a/9.2-2019.12/"
                   "binrel/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz")
BSP_INFO_NAME = "bsp_info.json"


def bsp_root(cfg: dict | None = None) -> Path:
    """BSP 公共目录：环境变量/配置 > ~/.cache/magnetar/bsp。"""
    v = os.environ.get("MAGNETAR_BSP_HOME") or (cfg or {}).get("MAGNETAR_BSP_HOME") or ""
    return Path(v).expanduser() if v else Path.home() / ".cache" / "magnetar" / "bsp"


def _run(cmd: list[str], timeout: int = 7200) -> str:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                       timeout=timeout, check=True)
    return p.stdout


def _download(url: str, dst: Path, timeout: int = 7200) -> None:
    if dst.is_file() and dst.stat().st_size > 0:
        return  # 已下载完成，直接复用
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = Path(f"{dst}.part")
    # aria2c 对格式不明的 all_proxy 环境变量会告警但继续；这里显式清掉避免噪音
    env = dict(os.environ)
    env.pop("all_proxy", None)
    env.pop("ALL_PROXY", None)
    subprocess.run(
        ["aria2c", "-c", "-x8", "-s8", "-k1M", "-d", str(dst.parent),
         "-o", part.name, url],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, env=env, timeout=timeout, check=True,
    )
    part.rename(dst)


def find_runtime_root(bsp_dir: Path, max_depth: int = 8) -> Path | None:
    """在 BSP 目录里找 AX runtime 根（含 include/ax_engine_api.h + lib/libax_engine.*）。"""
    if not Path(bsp_dir).is_dir():
        return None
    for root, dirs, files in os.walk(bsp_dir):
        rel = Path(root).relative_to(bsp_dir)
        if len(rel.parts) > max_depth:
            dirs[:] = []
            continue
        if "include" not in dirs or "lib" not in dirs:
            continue
        p = Path(root)
        if not (p / "include" / "ax_engine_api.h").is_file():
            continue
        if not any((p / "lib" / n).exists() for n in
                   ("libax_engine.so", "libax_engine.a", "libax_engine_tiny.so")):
            continue
        return p
    return None


def find_cross_compiler(bsp_dir: Path | None, max_depth: int = 8) -> Path | None:
    """找 aarch64 交叉编译器：AARCH64_GXX > PATH > BSP 目录内。"""
    env = os.environ.get("AARCH64_GXX")
    if env and Path(env).is_file():
        return Path(env)
    for name in ("aarch64-none-linux-gnu-g++", "aarch64-linux-gnu-g++"):
        p = shutil.which(name)
        if p:
            return Path(p)
    if bsp_dir and Path(bsp_dir).is_dir():
        # toolchain 目录优先（避免遍历整个大 SDK 树）
        search_roots = [Path(bsp_dir) / "toolchain", Path(bsp_dir)]
        for base in search_roots:
            if not base.is_dir():
                continue
            for root, dirs, files in os.walk(base):
                rel = Path(root).relative_to(base)
                if len(rel.parts) > max_depth:
                    dirs[:] = []
                    continue
                if "aarch64-none-linux-gnu-g++" in files:
                    return Path(root) / "aarch64-none-linux-gnu-g++"
    return None


def _load_cache(home: Path) -> dict | None:
    p = home / BSP_INFO_NAME
    if not p.is_file():
        return None
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if info.get("runtime_root") and Path(info["runtime_root"]).is_dir():
        return info
    return None


def _save_cache(home: Path, info: dict) -> None:
    (home / BSP_INFO_NAME).write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")


def _ensure_ax650(home: Path, cfg: dict | None, force: bool) -> dict | None:
    home.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cache(home)
        if cached:
            return cached
    tgz = home / AX650_SDK_TGZ
    if not tgz.is_file():
        url = ((os.environ.get("CXX_BSP_URL") or (cfg or {}).get("CXX_BSP_URL"))
               or modelscope_url(AX650_REPO, f"{AX650_SDK_SUBDIR}/{AX650_SDK_TGZ}"))
        print(f"[bsp_util] 下载 AX650 BSP SDK（约 3.7GB，仅一次）: {url}")
        _download(url, tgz)
    runtime = _ax650_runtime(home, tgz)
    _ensure_toolchain(home, cfg)
    gcc = find_cross_compiler(home)
    info = {
        "bsp_dir": str(home),
        "version": "V3.10.2",
        "runtime_root": str(runtime) if runtime else None,
        "cross_compiler": str(gcc) if gcc else None,
    }
    _save_cache(home, info)
    if runtime is None:
        print(f"[bsp_util] 警告: 未在 BSP 中找到 AX runtime（include/ax_engine_api.h），"
              f"C++ 编译不可用: {home}")
        return None
    print(f"[bsp_util] AX650 BSP 就绪: runtime={info['runtime_root']} "
          f"gcc={info['cross_compiler'] or '未找到'}")
    return info


def _ax650_runtime(home: Path, tgz: Path) -> Path | None:
    """解出 AX650 runtime（msp.tgz → msp/out），返回 runtime root。"""
    out = home / "msp" / "out"
    if (out / "include" / "ax_engine_api.h").is_file():
        return out
    pkg_msp = home / AX650_SDK_PKG_DIR / "package" / "msp.tgz"
    if not pkg_msp.is_file():
        print(f"[bsp_util] 从 BSP SDK 包中提取 msp.tgz")
        _run(["tar", "-xzf", str(tgz), "-C", str(home),
              f"{AX650_SDK_PKG_DIR}/package/msp.tgz"], timeout=10800)
    print(f"[bsp_util] 解压 AX runtime（msp.tgz）")
    _run(["tar", "-xzf", str(pkg_msp), "-C", str(home)], timeout=1800)
    if (out / "include" / "ax_engine_api.h").is_file():
        return out
    return find_runtime_root(home)


def _ensure_toolchain(home: Path, cfg: dict | None, force: bool = False) -> None:
    """确保 aarch64 交叉编译器就绪（Arm GNU 9.2，官方地址，CXX_TOOLCHAIN_URL 可覆盖）。"""
    if not force and find_cross_compiler(home) is not None:
        return
    url = (os.environ.get("CXX_TOOLCHAIN_URL")
           or (cfg or {}).get("CXX_TOOLCHAIN_URL") or ARM_GCC_9_2_URL)
    tc_dir = home / "toolchain"
    tc_dir.mkdir(parents=True, exist_ok=True)
    tarball = tc_dir / url.rsplit("/", 1)[-1]
    if not tarball.is_file():
        print(f"[bsp_util] 下载交叉编译器（约 270MB，仅一次）: {url}")
        _download(url, tarball)
    if find_cross_compiler(home) is None:
        _run(["tar", "-xJf", str(tarball), "-C", str(tc_dir)], timeout=1800)


def _ensure_ax620e(home: Path, cfg: dict | None, force: bool) -> dict | None:
    home.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cache(home)
        if cached:
            return cached
    runtime = find_runtime_root(home)
    if runtime is None:
        url = os.environ.get("CXX_BSP_URL") or (cfg or {}).get("CXX_BSP_URL")
        if url:
            tgz = home / "bsp.tar.gz"
            if not tgz.is_file():
                print(f"[bsp_util] 下载 AX620E BSP: {url}")
                _download(url, tgz)
            print(f"[bsp_util] 解压 AX620E BSP: {tgz.name}")
            _run(["tar", "-xzf", str(tgz), "-C", str(home)], timeout=10800)
            runtime = find_runtime_root(home)
    gcc = find_cross_compiler(home)
    info = {
        "bsp_dir": str(home),
        "runtime_root": str(runtime) if runtime else None,
        "cross_compiler": str(gcc) if gcc else None,
    }
    _save_cache(home, info)
    if runtime is None:
        print("[bsp_util] AX620E BSP 不可用（未配置 CXX_BSP_URL 且无本地缓存），"
              "C++ 编译降级跳过（CMake 仍可配置）")
        return None
    print(f"[bsp_util] AX620E BSP 就绪: runtime={info['runtime_root']}")
    return info


def ensure_bsp(target_hw: str = "AX650", cfg: dict | None = None,
               force: bool = False) -> dict | None:
    """确保目标芯片的 BSP 在公共目录就绪，返回 runtime/cross_compiler 信息。"""
    hw = (target_hw or "AX650").upper()
    root = bsp_root(cfg)
    if hw.startswith("AX650"):
        return _ensure_ax650(root / "ax650", cfg, force)
    if hw.startswith("AX620"):
        return _ensure_ax620e(root / "ax620e", cfg, force)
    print(f"[bsp_util] 未识别的目标芯片 {target_hw}，跳过 BSP 准备")
    return None


def build_cpp_sdk(task_dir: Path, cfg: dict | None = None,
                  target_hw: str = "AX650") -> Path | None:
    """用公共 BSP 交叉编译 sdk/cpp，返回可执行文件路径；不可用返回 None。"""
    bsp = ensure_bsp(target_hw, cfg)
    if not bsp or not bsp.get("runtime_root"):
        print("[bsp_util] BSP 不可用，跳过 C++ SDK 编译（不影响 Python SDK 与交付）")
        return None
    gcc = bsp.get("cross_compiler")
    if not gcc:
        print("[bsp_util] 未找到 aarch64 交叉编译器（AARCH64_GXX 或 BSP 内），跳过 C++ SDK 编译")
        return None
    cpp = Path(task_dir) / "sdk" / "cpp"
    if not (cpp / "CMakeLists.txt").is_file():
        print(f"[bsp_util] sdk/cpp 不存在，跳过: {cpp}")
        return None
    build = cpp / "build-aarch64"
    build.mkdir(parents=True, exist_ok=True)
    _run([
        "cmake", "-S", str(cpp), "-B", str(build),
        f"-DAX_RUNTIME_ROOT={bsp['runtime_root']}",
        f"-DCMAKE_CXX_COMPILER={gcc}",
    ], timeout=600)
    _run(["cmake", "--build", str(build), "-j8"], timeout=1200)
    for name in ("model_example", "mobilenet_example"):
        exe = build / name
        if exe.is_file():
            print(f"[bsp_util] C++ SDK 编译完成: {exe}")
            return exe
    print(f"[bsp_util] 编译完成但未找到可执行文件（检查 {build}）")
    return None
