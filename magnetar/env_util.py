"""模型转换环境复用：共享 base venv + 任务薄 venv。

痛点：每个模型都新建完整 venv，torch / onnxruntime / transformers 等大包重复安装
（1.4-6GB/份）。方案：

- ``ensure_base_env()``：一次性装好通用大包到 ``~/.cache/magnetar/base-venv``
  （``MAGNETAR_BASE_VENV`` 可覆盖），依赖清单哈希写 marker，清单变化才重建；
- ``create_task_venv()``：任务 venv 用 ``uv venv`` 创建，再写
  ``_magnetar_base.pth`` 把 base 的 site-packages 链接进来（任务本地包优先、
  base 兜底），大包零拷贝复用，只装模型特有依赖（小包，秒级），路径固化到
  ``TASK_DIR/config.json`` 的 ``VENV_PATH``；
- 后续阶段用 ``resolve_task_python(task_dir)`` 拿解释器，不再重复建环境。

CLI：``python -m magnetar.env_util base [--force]`` /
``python -m magnetar.env_util task <TASK_DIR> [--extra pkg ...]`` /
``python -m magnetar.env_util python <TASK_DIR>``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_REQ = REPO_ROOT / "requirements" / "base.txt"
BASE_ENV_DEFAULT = Path.home() / ".cache" / "magnetar" / "base-venv"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
MARKER_NAME = "magnetar_base.marker"
PYTHON_VERSION = "3.10"


def base_env_dir(cfg: dict | None = None) -> Path:
    """base venv 目录：环境变量/配置 > ~/.cache/magnetar/base-venv。"""
    v = os.environ.get("MAGNETAR_BASE_VENV") or (cfg or {}).get("MAGNETAR_BASE_VENV") or ""
    return Path(v).expanduser() if v else BASE_ENV_DEFAULT


def _req_hash() -> str:
    """base 依赖清单 + Python 版本指纹（变化即触发重建）。"""
    h = hashlib.sha256()
    h.update(BASE_REQ.read_bytes())
    h.update(f"\nPY={PYTHON_VERSION}".encode())
    return h.hexdigest()[:16]


def _marker(venv: Path) -> Path:
    return venv / MARKER_NAME


def _run(cmd: list[str], env: dict | None = None, timeout: int = 3600) -> None:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                   env=merged, timeout=timeout, check=True)


def _py_output(cmd: list[str], timeout: int = 120) -> str:
    """执行 python 并返回 stdout（用于探测 site-packages 路径）。"""
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                       env=dict(os.environ), timeout=timeout, check=True)
    return p.stdout.strip()


def _link_base_packages(venv: Path, base: Path) -> None:
    """在任务 venv 写 .pth 链接 base 的 site-packages（base 兜底，任务包优先）。"""
    base_site = _py_output([str(base / "bin" / "python"),
                            "-c", "import site; print(site.getsitepackages()[0])"])
    venv_site = _py_output([str(venv / "bin" / "python"),
                            "-c", "import site; print(site.getsitepackages()[0])"])
    pth = Path(venv_site) / "_magnetar_base.pth"
    pth.parent.mkdir(parents=True, exist_ok=True)
    pth.write_text(base_site + "\n", encoding="utf-8")


def _venv_lock(venv: Path):
    """base venv 重建互斥锁（防止多任务并发重建）。"""
    import contextlib

    @contextlib.contextmanager
    def _lock():
        lock = Path(f"{venv}.lock")
        deadline = time.time() + 1800
        while True:
            try:
                lock.mkdir()
                break
            except FileExistsError:
                if time.time() > deadline:
                    raise RuntimeError(f"等待 base venv 锁超时: {lock}")
                time.sleep(2)
        try:
            yield
        finally:
            lock.rmdir()

    return _lock()


def ensure_base_env(cfg: dict | None = None, force: bool = False,
                    quiet: bool = False) -> Path:
    """确保 base venv 存在且依赖清单未变；大包只装一次。"""
    from magnetar.net_util import uv_env

    venv = base_env_dir(cfg)
    py = venv / "bin" / "python"
    req_hash = _req_hash()
    if not force and py.is_file() and _marker(venv).is_file():
        if _marker(venv).read_text(encoding="utf-8").strip() == req_hash:
            return venv
        if not quiet:
            print(f"[env_util] base 依赖清单变化，重建 {venv}")
    if not quiet:
        print(f"[env_util] 准备 base venv: {venv}（torch CPU + 通用大包，首次较久）")
    with _venv_lock(venv):
        rebuild = force or not py.is_file()
        if not rebuild and _marker(venv).is_file():
            rebuild = _marker(venv).read_text(encoding="utf-8").strip() != req_hash
        if rebuild:
            # 清单变化/强制重建：清掉旧环境，避免残留包
            cmd = ["uv", "venv", "--python", PYTHON_VERSION]
            if venv.exists():
                cmd.append("--clear")
            _run([*cmd, str(venv)])
        # torch/torchvision 走 PyTorch CPU index，避免 CUDA 全家桶
        _run(["uv", "pip", "install", "--python", str(py),
              "--index-url", TORCH_CPU_INDEX, "torch", "torchvision"])
        # 其余通用依赖走默认 PyPI 镜像
        _run(["uv", "pip", "install", "--python", str(py),
              "-r", str(BASE_REQ)], env=uv_env(cfg))
        _marker(venv).write_text(req_hash, encoding="utf-8")
    if not quiet:
        print(f"[env_util] base venv 就绪: {venv}")
    return venv


def _task_config(task_dir: Path) -> dict:
    path = Path(task_dir) / "config.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_task_config(task_dir: Path, cfg: dict) -> None:
    path = Path(task_dir) / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def create_task_venv(task_dir: Path, cfg: dict | None = None,
                     extra_packages: tuple[str, ...] = (),
                     quiet: bool = False) -> Path:
    """任务薄 venv：复用 base 大包，只装模型特有依赖。

    返回任务 venv 路径，并固化到 TASK_DIR/config.json 的 VENV_PATH。
    """
    from magnetar.net_util import uv_env

    base = ensure_base_env(cfg, quiet=quiet)
    venv = Path(task_dir) / ".venv"
    py = venv / "bin" / "python"
    if not py.is_file():
        _run(["uv", "venv", "--python", str(base / "bin" / "python"),
              str(venv)])
        _link_base_packages(venv, base)
    if extra_packages:
        _run(["uv", "pip", "install", "--python", str(py),
              *extra_packages], env=uv_env(cfg))
    if not quiet:
        print(f"[env_util] 任务 venv 就绪: {venv}（复用 base，未重装大包）")
    task_cfg = _task_config(task_dir)
    task_cfg["VENV_PATH"] = str(venv)
    _write_task_config(task_dir, task_cfg)
    return venv


def resolve_task_python(task_dir: Path, cfg: dict | None = None) -> str:
    """取任务解释器：优先任务 venv，其次 base venv。"""
    task_cfg = _task_config(task_dir)
    for cand in (task_cfg.get("VENV_PATH", ""), base_env_dir(cfg)):
        if not cand:
            continue
        py = Path(cand) / "bin" / "python"
        if py.is_file():
            return str(py)
    return str(base_env_dir(cfg) / "bin" / "python")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Magnetar 模型转换环境工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("base", help="确保/重建共享 base venv").add_argument(
        "--force", action="store_true", help="强制重建")
    p_task = sub.add_parser("task", help="创建任务薄 venv（复用 base）")
    p_task.add_argument("task_dir")
    p_task.add_argument("--extra", nargs="*", default=(), help="模型特有依赖包")
    p_py = sub.add_parser("python", help="打印任务解释器路径")
    p_py.add_argument("task_dir")
    args = ap.parse_args(argv)
    if args.cmd == "base":
        ensure_base_env(force=args.force)
    elif args.cmd == "task":
        create_task_venv(Path(args.task_dir), extra_packages=tuple(args.extra or ()))
    elif args.cmd == "python":
        print(resolve_task_python(Path(args.task_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
