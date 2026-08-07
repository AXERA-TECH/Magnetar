"""Docker/Pulsar2 工具函数。

Token 效率约定：大输出（编译/仿真日志）默认只返回尾部，完整日志通过 log_file 落盘，
禁止把整段日志带回上下文。
"""
import os, re, subprocess
from pathlib import Path

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

def get_pulsar2_proto_enums(image: str) -> dict:
    """从 Pulsar2 Docker 镜像读取 common.proto，解析所有枚举定义。

    Returns:
        {"DataType": {"U8": 1, "FP32": 10, ...}, "ColorSpace": {...}, ...}
    """
    for proto_path in ["/opt/pulsar2/yamain/config/common.proto", "/opt/pulsar2/axnn/yamain/config/common.proto"]:
        try:
            raw = run(["docker", "run", "--rm", "--entrypoint", "cat", image, proto_path], timeout=30)
            break
        except RuntimeError:
            continue
    else:
        raise RuntimeError(f"Cannot find common.proto in Pulsar2 image {image}")
    enums: dict[str, dict[str, int]] = {}
    current = None
    for line in raw.splitlines():
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

# 缓存 proto 枚举，避免重复拉取
_proto_cache: dict[str, dict] = {}

def get_pulsar2_proto_enums_cached(image: str) -> dict:
    if image not in _proto_cache:
        _proto_cache[image] = get_pulsar2_proto_enums(image)
    return _proto_cache[image]
