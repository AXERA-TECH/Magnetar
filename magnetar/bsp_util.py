"""BSP / 交叉工具链公共目录管理。

痛点：C++ SDK 编译总报找不到 ax_engine 头文件/库——BSP 需要人肉下载，
``AX_RUNTIME_ROOT`` 没有来源。方案：

- BSP 统一放共享目录（``MAGNETAR_BSP_HOME``，默认 ``~/.cache/magnetar/bsp``），
  与 Pulsar2 独立包、base venv 同一套约定，多任务共享、只下载一次；
- SDK/runtime 下载地址以 ax-pipeline ``scripts/build_common.sh`` 为唯一来源
  （按芯片解析 ``MSP_URL_DEFAULT`` / ``TOOLCHAIN_URL_DEFAULT``；AX650 直接下
  约 60MB 的 msp zip，不再拉 ModelScope 3.7GB 全量 SDK）；
- ``ensure_bsp()`` 自动拉取清单/下载/解压/探测 runtime root 与交叉编译器；
- ``build_cpp_sdk()`` 用探测到的 runtime root + 交叉编译器一键 CMake 编译 C++ SDK。

芯片对应（AX620E 是 NPU 名称，对应 SoC 为 AX630C / AX620Q；build_common.sh 的 case 键）：
- AX650 → ``ax650``：msp_50_3.10.2.zip + Arm GNU 9.2 aarch64 交叉编译器；
- AX630C → ``ax630c``：msp_20e_3.0.0.zip + Arm GNU 9.2 aarch64 交叉编译器；
- AX620Q / AX620E → ``ax620q``：msp_20e_3.0.0.zip + ax620q_bsp_sdk uclibc
  交叉编译器（TARGET_HARDWARE 写 AX620E 时按 AX620Q 处理）。

``CXX_BSP_URL`` / ``CXX_TOOLCHAIN_URL`` 可覆盖下载地址；清单本身可用
``BUILD_COMMON_SH_URL`` 覆盖并缓存到 ``MAGNETAR_BSP_HOME/cache/``。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from magnetar.net_util import gh_proxy_url

BUILD_COMMON_URL = ("https://raw.githubusercontent.com/AXERA-TECH/ax-pipeline/"
                    "main/scripts/build_common.sh")
BSP_INFO_NAME = "bsp_info.json"
# build_common.sh 中需要解析的字段
_BC_KEYS = ("MSP_ZIP_NAME", "MSP_URL_DEFAULT",
            "TOOLCHAIN_ARCHIVE_NAME", "TOOLCHAIN_URL_DEFAULT", "COMPILER_CHECK")
# Magnetar 目标芯片 → build_common.sh case 键
CHIP_TO_BC = {"AX650": "ax650", "AX630C": "ax630c",
              "AX620E": "ax620q", "AX620Q": "ax620q"}


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
    """找交叉编译器：AARCH64_GXX > PATH > BSP 目录内（含 AX620Q uclibc）。"""
    env = os.environ.get("AARCH64_GXX")
    if env and Path(env).is_file():
        return Path(env)
    candidates = ("aarch64-none-linux-gnu-g++", "aarch64-linux-gnu-g++",
                  "arm-AX620E-linux-uclibcgnueabihf-g++")
    for name in candidates:
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
                for name in candidates:
                    if name in files:
                        return Path(root) / name
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


def _fetch_build_common(cfg: dict | None = None) -> str:
    """拉取 ax-pipeline build_common.sh（本地缓存，删缓存文件即刷新）。"""
    home = bsp_root(cfg)
    cache = home / "cache" / "build_common.sh"
    if cache.is_file() and cache.stat().st_size > 0:
        return cache.read_text(encoding="utf-8")
    url = (os.environ.get("BUILD_COMMON_SH_URL")
           or (cfg or {}).get("BUILD_COMMON_SH_URL") or BUILD_COMMON_URL)
    url = gh_proxy_url(url, cfg)
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            text = r.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"无法获取 ax-pipeline build_common.sh（{url}）: {e}")
    cache.write_text(text, encoding="utf-8")
    return text


def _parse_build_common(text: str) -> dict[str, dict[str, str]]:
    """解析 build_common.sh 的 case 分支，返回 {chip: {field: value}}。"""
    entries: dict[str, dict[str, str]] = {}
    chip: str | None = None
    for line in text.splitlines():
        m = re.match(r"^  ([a-z0-9_-]+)\)\s*(?:#.*)?$", line)
        if m:
            chip = m.group(1)
            entries.setdefault(chip, {})
            continue
        if line.strip() in (";;", "esac"):
            chip = None
            continue
        if chip is None:
            continue
        for key in _BC_KEYS:
            m2 = re.match(rf'^    {re.escape(key)}="([^"]*)"', line)
            if m2:
                entries[chip][key] = m2.group(1)
                break
    return entries


def _chip_entry(chip: str, cfg: dict | None = None) -> dict:
    """取 build_common.sh 中某芯片的下载信息（已展开 ${...} 变量）。"""
    text = _fetch_build_common(cfg)
    entries = _parse_build_common(text)
    bc_key = CHIP_TO_BC.get((chip or "").upper(), chip)
    entry = entries.get(bc_key)
    if not entry:
        raise RuntimeError(
            f"build_common.sh 中没有芯片 {chip}（case 键 {bc_key}）的下载地址")
    return {
        "msp_zip_name": entry.get("MSP_ZIP_NAME", ""),
        "msp_url": entry.get("MSP_URL_DEFAULT", ""),
        "toolchain_url": entry.get("TOOLCHAIN_URL_DEFAULT", "").replace(
            "${TOOLCHAIN_ARCHIVE_NAME}",
            entry.get("TOOLCHAIN_ARCHIVE_NAME", "")),
        "compiler_check": entry.get("COMPILER_CHECK", ""),
    }


def _bsp_url(entry: dict | None, cfg: dict | None = None) -> str:
    """BSP/runtime 下载地址：CXX_BSP_URL > build_common.sh 默认。"""
    return (os.environ.get("CXX_BSP_URL") or (cfg or {}).get("CXX_BSP_URL")
            or (entry or {}).get("msp_url") or "")


def _msp_archive(home: Path, entry: dict | None, cfg: dict | None = None) -> Path:
    """BSP/runtime 压缩包落盘路径：默认 build_common.sh 文件名，CXX_BSP_URL 用 URL 末段。"""
    url = _bsp_url(entry, cfg)
    if os.environ.get("CXX_BSP_URL") or (cfg or {}).get("CXX_BSP_URL"):
        name = url.rsplit("/", 1)[-1] or "msp.zip"
    else:
        name = ((entry or {}).get("msp_zip_name")
                or url.rsplit("/", 1)[-1] or "msp.zip")
    return home / name


def _archive_version(archive: Path) -> str:
    m = re.search(r"(\d+\.\d+\.\d+)", archive.name)
    return f"V{m.group(1)}" if m else ""


def _ensure_ax650(home: Path, cfg: dict | None, force: bool) -> dict | None:
    home.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cache(home)
        if cached:
            return cached
    entry = _chip_entry("ax650", cfg)
    msp_zip = _msp_archive(home, entry, cfg)
    if not msp_zip.is_file():
        url = _bsp_url(entry, cfg)
        print(f"[bsp_util] 下载 AX650 runtime（msp zip，约 60MB，仅一次）: {url}")
        _download(url, msp_zip)
    runtime = _extract_bsp_archive(home, msp_zip)
    _ensure_toolchain(home, cfg, entry)
    gcc = find_cross_compiler(home)
    info = {
        "bsp_dir": str(home),
        "version": _archive_version(msp_zip),
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


def _extract_bsp_archive(home: Path, archive: Path) -> Path | None:
    """解压 BSP/runtime 压缩包（zip/tar/tgz），返回 AX runtime root；无则 None。"""
    out = home / "msp" / "out"
    if (out / "include" / "ax_engine_api.h").is_file():
        return out
    if not archive.is_file():
        return None
    dest = home
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as z:
            top = {n.split("/", 1)[0] for n in z.namelist()
                   if "/" in n or n.endswith("/")}
        # zip 顶层不是单一 msp/ 目录时，解到独立子目录避免混入 home
        if top != {"msp"}:
            dest = home / archive.stem
            dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as t:
            t.extractall(dest)
    runtime = find_runtime_root(home)
    if runtime is None and (out / "include" / "ax_engine_api.h").is_file():
        runtime = out
    return runtime


def _ensure_toolchain(home: Path, cfg: dict | None, entry: dict | None = None,
                      force: bool = False) -> None:
    """确保交叉编译器就绪（地址来自 build_common.sh，CXX_TOOLCHAIN_URL 可覆盖）。"""
    if not force and find_cross_compiler(home) is not None:
        return
    url = (os.environ.get("CXX_TOOLCHAIN_URL")
           or (cfg or {}).get("CXX_TOOLCHAIN_URL")
           or (entry or {}).get("toolchain_url") or "")
    if not url:
        print("[bsp_util] 交叉编译器下载地址不可用（未配置 CXX_TOOLCHAIN_URL），"
              "C++ 编译将降级")
        return
    tc_dir = home / "toolchain"
    tc_dir.mkdir(parents=True, exist_ok=True)
    tarball = tc_dir / url.rsplit("/", 1)[-1]
    if not tarball.is_file():
        print(f"[bsp_util] 下载交叉编译器: {url}")
        _download(url, tarball)
    if find_cross_compiler(home) is None:
        args = ["tar", "-xzf", str(tarball), "-C", str(tc_dir)]
        if str(tarball).endswith(".xz"):
            args = ["tar", "-xJf", str(tarball), "-C", str(tc_dir)]
        _run(args, timeout=1800)


def _ensure_chip(home: Path, bc_key: str, cfg: dict | None,
                 force: bool) -> dict | None:
    """AX620E 家族（ax630c / ax620q）：按 build_common.sh 下载 runtime + 编译器。"""
    home.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cache(home)
        if cached:
            return cached
    entry = None
    try:
        entry = _chip_entry(bc_key, cfg)
    except RuntimeError as e:
        print(f"[bsp_util] {e}")
    url = _bsp_url(entry, cfg)
    archive = None
    if url:
        archive = _msp_archive(home, entry, cfg)
        if not archive.is_file():
            print(f"[bsp_util] 下载 {bc_key} runtime: {url}")
            _download(url, archive)
        _extract_bsp_archive(home, archive)
    _ensure_toolchain(home, cfg, entry)
    runtime = find_runtime_root(home)
    gcc = find_cross_compiler(home)
    info = {
        "bsp_dir": str(home),
        "version": _archive_version(archive) if archive else "",
        "runtime_root": str(runtime) if runtime else None,
        "cross_compiler": str(gcc) if gcc else None,
    }
    _save_cache(home, info)
    if runtime is None:
        print(f"[bsp_util] {bc_key} BSP 不可用（未配置 CXX_BSP_URL 且无本地缓存），"
              "C++ 编译降级跳过（CMake 仍可配置）")
        return None
    print(f"[bsp_util] {bc_key} BSP 就绪: runtime={info['runtime_root']} "
          f"gcc={info['cross_compiler'] or '未找到'}")
    return info


def ensure_bsp(target_hw: str = "AX650", cfg: dict | None = None,
               force: bool = False) -> dict | None:
    """确保目标芯片的 BSP 在公共目录就绪，返回 runtime/cross_compiler 信息。"""
    hw = (target_hw or "AX650").upper()
    root = bsp_root(cfg)
    if hw.startswith("AX650"):
        return _ensure_ax650(root / "ax650", cfg, force)
    if hw.startswith("AX630"):
        return _ensure_chip(root / "ax630c", "ax630c", cfg, force)
    if hw.startswith("AX620"):
        return _ensure_chip(root / "ax620e", "ax620q", cfg, force)
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
