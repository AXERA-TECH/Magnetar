"""Pulsar2 执行后端工具函数。

支持两种后端：
- 独立安装包（默认，推荐）：``ax_pulsar2_*_package.tar.gz`` 解压目录，
  用 ``PULSAR2_HOME`` 环境变量/.magnetarrc 指定，或自动扫描
  ``~/.cache/magnetar/pulsar2/<版本>/``；无需 docker daemon/mount/chown，
  license 由 bin/pulsar2 自动装到 ~/.hasplm。
- Docker 镜像（兜底）：保留原 docker 路径，句柄 ``img:<image>``。

句柄约定：``pkg:<绝对路径>`` / ``img:<镜像名>``；裸字符串按镜像名兼容。

Token 效率约定：大输出（编译/仿真日志）默认只返回尾部，完整日志通过 log_file 落盘，
禁止把整段日志带回上下文。
"""
import os, re, shutil, subprocess, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTO_CACHE_ROOT = Path(os.environ.get("MAGNETAR_PROTO_CACHE", REPO_ROOT / "cache" / "pulsar2"))
PROTO_ROOTS = [
    "/opt/pulsar2/yamain/config",       # Pulsar2 6.0
    "/opt/pulsar2/axnn/yamain/config",  # Pulsar2 7.0
]

DEFAULT_TAIL_LINES = 400

def _tail(text: str, lines: int | None, chars: int | None = None) -> str:
    if lines:
        text = "\n".join(text.splitlines()[-lines:])
    elif not text:
        return text
    if chars and len(text) > chars:
        return "…[截断] " + text[-chars:]
    return text

def run(cmd, cwd=None, timeout=600, max_tail=None, log_file=None):
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if log_file:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        detail = _tail(proc.stdout, max_tail or DEFAULT_TAIL_LINES, chars=4000)
        raise RuntimeError(
            f"Command failed (exit {proc.returncode}): {' '.join(cmd)}\n{detail}"
            + (f"\n(完整日志: {log_file})" if log_file else "")
        )
    return _tail(proc.stdout, max_tail) if max_tail else proc.stdout

def latest_pulsar2_image() -> str:
    output = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=30)
    candidates = []
    for image in output.splitlines():
        repo, _, tag = image.partition(":")
        if repo != "pulsar2": continue
        m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", tag)
        if not m: continue
        candidates.append((tuple(int(x or 0) for x in m.groups()), image))
    if not candidates: raise RuntimeError("No pulsar2:* Docker image. Run: ./scripts/install_pulsar2.sh")
    return max(candidates, key=lambda x: x[0])[1]


# ─── 后端解析（独立包优先，docker 兜底） ───

def _cfg_value(cfg: dict | None, key: str) -> str:
    v = os.environ.get(key)
    if not v and cfg:
        v = str(cfg.get(key) or "")
    return (v or "").strip()


def find_pulsar2_home(cfg: dict | None = None) -> Path | None:
    """定位官方独立安装包目录（含 bin/pulsar2）。"""
    home = _cfg_value(cfg, "PULSAR2_HOME")
    if home:
        p = Path(home).expanduser()
        return p if (p / "bin" / "pulsar2").is_file() else None
    base = Path.home() / ".cache" / "magnetar" / "pulsar2"
    if base.is_dir():
        for d in sorted(base.iterdir(), key=lambda p: p.name, reverse=True):
            if (d / "bin" / "pulsar2").is_file():
                return d
    for p in (Path("/opt/pulsar2"),):
        if (p / "bin" / "pulsar2").is_file():
            return p
    return None


def resolve_backend(cfg: dict | None = None) -> str:
    """返回后端句柄：有独立包 → ``pkg:<home>``，否则 docker 镜像 → ``img:<image>``。"""
    home = find_pulsar2_home(cfg)
    if home is not None:
        return f"pkg:{home}"
    return f"img:{latest_pulsar2_image()}"


def parse_backend(handle: str):
    """解析后端句柄 → (kind, name)；裸字符串按 docker 镜像兼容。"""
    if isinstance(handle, str) and handle.startswith("pkg:"):
        return ("package", handle[4:])
    if isinstance(handle, str) and handle.startswith("img:"):
        return ("docker", handle[4:])
    return ("docker", handle)


def package_env(home: Path) -> dict:
    """独立包运行环境（与官方 bin/pulsar2 启动器保持一致）。"""
    ws = Path(home)
    lib = os.environ.get("PULSAR2_LIB_PATH") or str(ws / "lib")
    pyhome = os.environ.get("PULSAR2_PYTHON_PATH") or str(ws / "python3")
    env = os.environ.copy()
    env.update({
        "PULSAR2_LIB_PATH": lib,
        "PULSAR2_PYTHON_PATH": pyhome,
        "PATH": str(ws / "bin") + os.pathsep + os.environ.get("PATH", ""),
    })
    # 只在对应目录存在时才覆写（精简模式/测试环境用系统 python 时避免破坏解释器）
    if (ws / "lib").is_dir():
        env["LD_LIBRARY_PATH"] = lib
    if (ws / "python3" / "bin" / "python3").is_file():
        env["PYTHONHOME"] = pyhome
    if (ws / "pulsar2").is_dir():
        env["PYTHONPATH"] = os.pathsep.join([
            str(ws / "pulsar2" / "axnn"),
            str(ws / "pulsar2" / "axnn" / "axnn" / "tools"),
            str(ws / "pulsar2"),
        ])
    return env


def _package_python_cmd(home: Path) -> list[str]:
    """返回独立包内置 python 的执行命令（带 loader，与启动器一致）。"""
    py = Path(home) / "python3" / "bin" / "python3"
    loader = Path(home) / "lib" / "ld-linux-x86-64.so.2"
    if not py.is_file():
        return ["python3"]  # 精简模式：用系统 python
    if loader.is_file():
        return [str(loader), str(py)]
    return [str(py)]


def _package_main_py(home: Path) -> Path | None:
    """定位独立包内的 pulsar2 入口 main.py（兼容 7.0 lite 与旧布局）。"""
    for rel in (
        "pulsar2/axnn/yamain/main.py",
        "pulsar2/axnn/axnn/yamain/main.py",
    ):
        p = home / rel
        if p.is_file():
            return p
    return None


def _ensure_package_license(home: Path) -> None:
    """把包内 install/*.v2c 装到 ~/.hasplm（官方启动器的 license 逻辑）。"""
    src = list((home / "install").glob("*.v2c"))
    if not src:
        return
    dst = Path.home() / ".hasplm" / "installed" / "32434"
    for v2c in src:
        if not (dst / v2c.name).exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(v2c, dst / v2c.name)


def run_pulsar2(handle: str, workspace: str, command: str, timeout=1800,
                log_file=None, max_tail=DEFAULT_TAIL_LINES) -> str:
    """按后端执行 Pulsar2 命令；command 形如 ``pulsar2 build --config ...``。"""
    kind, name = parse_backend(handle)
    if kind == "package":
        home = Path(name)
        parts = command.split()
        env = package_env(home)
        i = 0
        # 支持命令前缀环境变量（如 FLOAT_MATMUL_USE_CONV_EU=1 pulsar2 ...）
        while i < len(parts) and "=" in parts[i] and not parts[i].startswith("--"):
            k, v = parts[i].split("=", 1)
            env[k] = v
            i += 1
        if i < len(parts) and parts[i] == "pulsar2":
            i += 1
        main = _package_main_py(home)
        if main is None:
            raise RuntimeError(f"独立包缺少 pulsar2 入口（yamain/main.py）: {home}")
        _ensure_package_license(home)
        proc = subprocess.run(
            [*_package_python_cmd(home), str(main), *parts[i:]],
            cwd=workspace, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, timeout=timeout,
        )
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            Path(log_file).write_text(proc.stdout, encoding="utf-8")
        if proc.returncode != 0:
            detail = _tail(proc.stdout, max_tail or DEFAULT_TAIL_LINES, chars=4000)
            raise RuntimeError(
                f"Pulsar2 failed (exit {proc.returncode}): {command}\n{detail}"
                + (f"\n(完整日志: {log_file})" if log_file else "")
            )
        return _tail(proc.stdout, max_tail) if max_tail else proc.stdout
    return docker_pulsar2(name, workspace, command, timeout=timeout,
                          log_file=log_file, max_tail=max_tail)

def docker_pulsar2(image: str, workspace: str, command: str, timeout=1800,
                   log_file=None, max_tail=DEFAULT_TAIL_LINES) -> str:
    """跑 Pulsar2 命令；默认只返回日志尾部，log_file 指定时完整日志落盘。"""
    uid, gid = os.getuid(), os.getgid()
    # 授权：镜像内 /root/*.v2c 需在启动时装入 /root/.hasplm/installed/32434/，
    # 否则 assemble 阶段报 Sentinel key not found (H0007)（见 issues/013）
    wrapped = (
        "set +e; mkdir -p /root/.hasplm/installed/32434 && "
        "cp -f /root/*.v2c /root/.hasplm/installed/32434/ 2>/dev/null; "
        f"PATH=/usr/local/bin/.venv/bin:/opt/pulsar2:$PATH {command}; "
        f"status=$?; chown -R {uid}:{gid} /workspace; exit $status"
    )
    # Pulsar2 7.0 driverless license needs the license dir mounted at /root/.hasplm
    # (source dir can be overridden with MAGNETAR_HASP_SRC; default is the old verify home).
    hasp_src = os.environ.get("MAGNETAR_HASP_SRC", "/tmp/p2_verify_home/.hasplm")
    return run(["docker", "run", "--rm", "--network", "host",
                "-v", f"{workspace}:/workspace",
                "-v", "/var/hasplm:/var/hasplm",
                "-v", f"{hasp_src}:/root/.hasplm",
                "-e", "HASP_HOME=/root/.hasplm",
                image, "-lc", wrapped],
               timeout=timeout, log_file=log_file, max_tail=max_tail)

def make_writable(task_dir: str):
    from pathlib import Path
    if not Path(task_dir).exists(): return
    img = latest_pulsar2_image()
    uid, gid = os.getuid(), os.getgid()
    run(["docker", "run", "--rm", "-v", f"{task_dir}:/workspace", img, "-lc", f"chown -R {uid}:{gid} /workspace"], timeout=120)


_CONFIG_CHECK_SCRIPT = """\
import sys
sys.path.insert(0, "/opt/pulsar2")
from google.protobuf.json_format import ParseDict
import commentjson
from axnn.yamain.config.build_config_pb2 import BuildConfig

cfg_path = sys.argv[1]
msg = BuildConfig()
with open(cfg_path, encoding="utf-8") as f:
    d = commentjson.load(f)
try:
    ParseDict(d, msg)
except Exception as e:
    print(f"CONFIG_ERROR: {e}")
    sys.exit(1)
print(f"config-check OK: model_type={msg.model_type} "
      f"target_hardware={msg.target_hardware} npu_mode={msg.npu_mode}")
"""


def docker_pulsar2_config_check(
    handle: str,
    workspace: str,
    config_rel: str = "compile/pulsar2_config.json",
    timeout: int = 120,
) -> str:
    """用 Pulsar2 自身 build_config_pb2 解析配置（权威字段校验）。

    编译前跑一次（秒级）：任何未知字段/类型/枚举错误都会被 ParseDict 以
    字段级信息暴露，避免等完整编译几分钟后才失败。
    """
    kind, name = parse_backend(handle)
    if kind == "package":
        return _package_config_check(Path(name), workspace, config_rel, timeout)
    image = name
    script_path = Path(workspace) / "compile" / "_config_check.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_CONFIG_CHECK_SCRIPT, encoding="utf-8")
    cmd = [
        "docker", "run", "--rm", "--entrypoint", "/bin/bash",
        "-v", f"{workspace}:/workspace",
        image, "-lc",
        "PY=/usr/local/bin/.venv/bin/python3; [ -x \"$PY\" ] || PY=python3; "
        "\"$PY\" "
        f"/workspace/{config_rel.rsplit('/', 1)[0]}/_config_check.py "
        f"/workspace/{config_rel}",
    ]
    return run(cmd, timeout=timeout, max_tail=80)


def _package_config_check(home: Path, workspace: str, config_rel: str,
                          timeout: int = 120) -> str:
    """独立包本地 config-check：直接用包内 python + build_config_pb2。"""
    script_path = Path(workspace) / "compile" / "_config_check.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_CONFIG_CHECK_SCRIPT, encoding="utf-8")
    proc = subprocess.run(
        [*_package_python_cmd(home), str(script_path), str(Path(workspace) / config_rel)],
        cwd=workspace, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=package_env(home), timeout=timeout,
    )
    out = _tail(proc.stdout, 80, chars=4000)
    if proc.returncode != 0:
        raise RuntimeError(f"config-check failed (exit {proc.returncode}):\n{out}")
    return out

def parse_proto_enums(text: str) -> dict[str, dict[str, int]]:
    """解析 proto 文本中的 enum 定义，返回 {"EnumName": {"MEMBER": 0, ...}}。"""
    enums: dict[str, dict[str, int]] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r'^enum\s+(\w+)\s*\{', line)
        if m:
            current = m.group(1)
            enums[current] = {}
            continue
        m = re.match(r'^\s+(\w+)\s*=\s*(\d+)\s*;', line)
        if m and current:
            enums[current][m.group(1)] = int(m.group(2))
        if line.strip() == '}' and current:
            current = None
    return enums


def _proto_cache_dir(image: str) -> Path:
    tag = re.sub(r'[^A-Za-z0-9_.-]', '_', image)
    return PROTO_CACHE_ROOT / tag


def _read_proto_from_image(image: str, proto_name: str) -> str:
    """从镜像读取指定 proto 文件（兼容 6.0/7.0 两种目录布局）。"""
    last_err = None
    for root in PROTO_ROOTS:
        path = f"{root}/{proto_name}"
        try:
            return run(["docker", "run", "--rm", "--entrypoint", "cat", image, path], timeout=30)
        except RuntimeError as e:
            last_err = e
    raise RuntimeError(f"Cannot find {proto_name} in Pulsar2 image {image} ({last_err})")


def extract_pulsar2_proto(handle: str, force: bool = False) -> dict[str, Path]:
    """提取 Pulsar2 的 common.proto + build_config.proto 到本地缓存。

    后续工作流（枚举校验、配置生成）优先读本地文件，避免反复 docker run；
    人也可以直接打开缓存目录阅读 proto 内容。

    Args:
        handle: 后端句柄（pkg:<home> / img:<image>，裸字符串按镜像兼容）
        force: 强制重新提取（默认本地已有则跳过 docker）

    Returns:
        {"common.proto": Path, "build_config.proto": Path}
    """
    kind, name = parse_backend(handle)
    if kind == "package":
        return _extract_package_proto(Path(name), force)
    image = name
    out_dir = _proto_cache_dir(image)
    files = {name: out_dir / name for name in ("common.proto", "build_config.proto")}
    if not force and all(p.is_file() for p in files.values()):
        return files
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, path in files.items():
        try:
            raw = _read_proto_from_image(image, name)
            path.write_text(raw, encoding="utf-8")
        except OSError as e:
            print(f"[docker_util] 警告: 缓存 {path} 写入失败（{e}），本次仍使用 docker 读取", file=sys.stderr)
    return files


def _extract_package_proto(home: Path, force: bool = False) -> dict[str, Path]:
    """从独立包目录直接拷贝 proto（无需 docker）。"""
    cfg_dir = home / "pulsar2" / "axnn" / "yamain" / "config"
    out_dir = PROTO_CACHE_ROOT / f"pkg_{home.name}"
    files = {n: out_dir / n for n in ("common.proto", "build_config.proto")}
    if not force and all(p.is_file() for p in files.values()):
        return files
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, dst in files.items():
        src = cfg_dir / name
        if src.is_file():
            dst.write_bytes(src.read_bytes())
    missing = [n for n, p in files.items() if not p.is_file()]
    if missing:
        raise RuntimeError(f"独立包缺少 proto 文件: {cfg_dir}（{', '.join(missing)}）")
    return files


def get_pulsar2_proto_enums(handle: str) -> dict:
    """读取 Pulsar2 common.proto 枚举（优先本地缓存），返回枚举 dict。"""
    files = extract_pulsar2_proto(handle)
    raw = files["common.proto"].read_text(encoding="utf-8")
    return parse_proto_enums(raw)

# 缓存 proto 枚举，避免重复拉取
_proto_cache: dict[str, dict] = {}

def get_pulsar2_proto_enums_cached(handle: str) -> dict:
    if handle not in _proto_cache:
        _proto_cache[handle] = get_pulsar2_proto_enums(handle)
    return _proto_cache[handle]
