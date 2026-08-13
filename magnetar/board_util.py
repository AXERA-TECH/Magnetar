"""AX 板端 SSH/SCP/daemon 工具函数。

上板前用 ensure_remote_infer() 确保 ax_remote_infer daemon 已装并监听 18500，
装好后即可通过扫描 18500 端口发现板子（select_board 在 dashboard 不可用时回退端口扫描）。

board_lease(): 板端独占租约——多任务/多人共用一块板时，用原子 mkdir 抢锁；
租约目录 mtime 作心跳（超过 TTL 未续租自动视为过期），清理只删自己的 token
目录，杜绝误清别人环境。上板临时文件一律放进租约命名空间下。
"""
import json, os, re, subprocess, urllib.parse, urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from magnetar.net_util import gh_proxy_url

DASHBOARD = os.environ.get("MAGNETAR_BOARD_DASHBOARD", "http://10.126.35.22:25000/api/devices")
REMOTE_INFER_PORT = 18500
BOARD_LEASE_ROOT = "/tmp/magnetar-lease"
DEFAULT_LEASE_TTL = 1800  # 30 分钟；超时未续租的租约会被其他任务安全清理
AX_REMOTE_INFER_URL = (
    "https://github.com/AXERA-TECH/ax-remote-infer/releases/download/"
    "latest/ax-remote-infer-latest.zip"
)


class BoardBusyError(RuntimeError):
    """板子已被其他任务/用户占用。"""


@dataclass
class BoardLease:
    board: dict
    token: str
    dir: str
    work_root: str
    owner: str
    ttl: int

def _ssh_base(b): return ["sshpass", "-p", b["password"], "ssh", "-n", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", "-p", str(b["port"]), f"{b['user']}@{b['host']}"]
def _scp_base(b): return ["sshpass", "-p", b["password"], "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-P", str(b["port"])]

def ssh(board: dict, cmd: str, timeout=120, max_tail=None) -> str:
    """远程执行命令；max_tail 指定时只返回尾部（大输出建议用，完整输出不回上下文）。"""
    proc = subprocess.run(_ssh_base(board) + [cmd], text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout)
    if proc.returncode != 0:
        detail = "\n".join(proc.stdout.splitlines()[- (max_tail or 300):])
        raise RuntimeError(f"Remote failed (exit {proc.returncode}): {cmd}\n{detail}")
    if max_tail:
        return "\n".join(proc.stdout.splitlines()[-max_tail:])
    return proc.stdout

def scp_to(board: dict, src: str | Path, dst: str):
    from magnetar.docker_util import run as _r
    a = _scp_base(board)
    if Path(src).is_dir(): a.append("-r")
    _r(a + [str(src), f"{board['user']}@{board['host']}:{dst}"], timeout=240)

def scp_from(board: dict, src: str, dst: str | Path, recursive: bool = False):
    from magnetar.docker_util import run as _r
    a = _scp_base(board)
    if recursive or src.endswith("include"):
        a.append("-r")
    _r(a + [f"{board['user']}@{board['host']}:{src}", str(dst)], timeout=240)

def select_board(target_hw: str, pwd: str = "123456") -> dict | None:
    explicit = os.environ.get("MAGNETAR_BOARD")
    if explicit:
        p = urllib.parse.urlparse(explicit if "://" in explicit else f"ssh://{explicit}")
        u, h, port = p.username or "root", p.hostname, p.port or 22
        if not h: raise RuntimeError(f"Invalid MAGNETAR_BOARD: {explicit}")
        ct = ssh({"user": u, "host": h, "port": port, "password": pwd}, "cat /proc/ax_proc/chip_type 2>/dev/null || hostname", 20).strip()
        if target_hw.lower() not in ct.lower(): raise RuntimeError(f"Board chip {ct!r} != {target_hw}")
        return {"user": u, "host": h, "port": port, "password": pwd, "chip_type": ct}
    try:
        with urllib.request.urlopen(DASHBOARD, timeout=10) as r: devices = json.load(r).get("devices", [])
        for d in devices:
            if target_hw.lower() not in str(d.get("chip_type", "")).lower(): continue
            if d.get("is_occupied"): continue
            h = d.get("ip") or d.get("host")
            if not h: continue
            return {"user": d.get("default_user") or "root", "host": h, "port": int(d.get("ssh_port") or 22), "password": pwd, "chip_type": str(d.get("chip_type", ""))}
    except Exception: pass
    # 3. 兜底：扫描网段 18500 端口，发现装了 ax_remote_infer 的板子
    try:
        b = _scan_subnet_for_boards(_default_scan_subnet(), target_hw, pwd)
        if b is not None:
            return b
    except Exception:
        pass
    return None


def port_open(host: str, port: int = REMOTE_INFER_PORT, timeout: float = 2.0) -> bool:
    """TCP 端口连通性检查（用于判断 ax_remote_infer daemon 是否在跑）。"""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_remote_infer(board: dict, cache_dir: str | Path | None = None) -> dict:
    """上板前确保 ax_remote_infer daemon 已安装并监听 18500。

    - 18500 已通：不打扰板子，直接返回 running
    - 未通：下载官方 release 到本地缓存，用 remote_install.sh 静默安装，再验证端口
    装好后该板子即可通过扫描 18500 端口被发现。
    """
    host = board["host"]
    if port_open(host, REMOTE_INFER_PORT):
        return {"status": "running", "host": host, "installed": True}
    cache = Path(cache_dir or os.environ.get("MAGNETAR_AXINFER_CACHE")
                 or Path.home() / ".cache" / "magnetar" / "ax-remote-infer")
    cache.mkdir(parents=True, exist_ok=True)
    zip_path = cache / "ax-remote-infer-latest.zip"
    if not zip_path.exists() or not _is_valid_zip(zip_path):
        print(f"[board_util] {host}:18500 不通，下载 ax-remote-infer release ...")
        url = os.environ.get("AX_REMOTE_INFER_URL") or gh_proxy_url(AX_REMOTE_INFER_URL)
        _download_axinferelease(url, zip_path)
    release_dir = cache / "release"
    installer = release_dir / "remote_install.sh"
    if not installer.exists():
        import zipfile
        release_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(release_dir)
    if not installer.exists():
        raise RuntimeError(f"ax-remote-infer release 中缺少 remote_install.sh: {installer}")
    os.chmod(installer, 0o755)
    log = cache / f"install_{host}.log"
    cmd = [
        str(installer), host,
        "--user", str(board.get("user", "root")),
        "--pass", str(board.get("password", "123456")),
        "--port", str(board.get("port", 22)),
    ]
    print(f"[board_util] 静默安装 ax_remote_infer 到 {host}（SSH {board.get('user', 'root')}@{host}:{board.get('port', 22)}）...")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=600)
    log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(
            f"ax_remote_infer 安装失败（exit {proc.returncode}），日志: {log}\n{proc.stdout[-2000:]}"
        )
    if not port_open(host, REMOTE_INFER_PORT, timeout=5.0):
        raise RuntimeError(f"ax_remote_infer 安装后 {host}:18500 仍不通，请手动检查板子（日志: {log}）")
    return {"status": "installed", "host": host, "installed": True}


_PROBE_SCRIPT = r"""
set +e
echo '## chip'
cat /proc/ax_proc/chip_type 2>/dev/null || hostname
echo '## ax_run_model'
command -v ax_run_model
for p in /opt/bin/ax_run_model /usr/bin/ax_run_model; do [ -x "$p" ] && echo "$p"; done
echo '## python'
python3 --version 2>&1
echo '## pyaxengine'
python3 -c "import axengine as a; print('ok', getattr(a, '__version__', ''))" 2>&1
echo '## libax_engine'
ldconfig -p 2>/dev/null | grep -i ax_engine
for p in /usr/local/lib/libax_engine.so* /soc/lib/libax_engine.so* /opt/lib/libax_engine.so*; do
  [ -e "$p" ] && echo "$p"
done
echo '## ld_path'
echo "$LD_LIBRARY_PATH"
"""


def probe_board_env(board: dict, timeout: int = 120) -> dict:
    """SSH 探测板端推理环境，返回结构化 dict（缺什么一目了然）。

    Returns:
        chip_type / ax_run_model（首个可用路径或 None）/ ax_run_model_paths /
        python_version / pyaxengine（版本或 None）/ pyaxengine_error /
        libax_engine（路径列表）/ ld_library_path（板端原始 LD_LIBRARY_PATH）
    """
    out = ssh(board, _PROBE_SCRIPT, timeout=timeout, max_tail=300)
    env = parse_board_probe(out)
    env["host"] = board["host"]
    return env


def parse_board_probe(out: str) -> dict:
    """解析 probe_board_env 的 SSH 输出（纯函数，便于单测）。"""
    result: dict = {
        "chip_type": "",
        "ax_run_model": None,
        "ax_run_model_paths": [],
        "python_version": "",
        "pyaxengine": None,
        "pyaxengine_error": "",
        "libax_engine": [],
        "ld_library_path": "",
    }
    section = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line:
            continue
        if section == "chip":
            if not result["chip_type"]:
                result["chip_type"] = line
        elif section == "ax_run_model":
            if line.startswith("/") and line not in result["ax_run_model_paths"]:
                result["ax_run_model_paths"].append(line)
        elif section == "python":
            if not result["python_version"]:
                result["python_version"] = line
        elif section == "pyaxengine":
            if line.startswith("ok"):
                result["pyaxengine"] = line[3:].strip() or "unknown"
            elif not result["pyaxengine_error"]:
                result["pyaxengine_error"] = line
        elif section == "libax_engine":
            path = line
            if "=>" in line:
                path = line.split("=>", 1)[1].strip()
            if path.startswith("/") and path not in result["libax_engine"]:
                result["libax_engine"].append(path)
        elif section == "ld_path":
            result["ld_library_path"] = line
    if result["ax_run_model_paths"]:
        result["ax_run_model"] = result["ax_run_model_paths"][0]
    return result


def suggest_ld_library_path(env: dict) -> str:
    """由探测结果推导板端 LD_LIBRARY_PATH（先探测到的 .so 目录，再补常用目录）。"""
    dirs: list[str] = []
    for p in env.get("libax_engine", []):
        parent = str(Path(p).parent)
        if parent not in dirs:
            dirs.append(parent)
    for extra in ("/soc/lib", "/usr/local/lib", "/opt/lib"):
        if extra not in dirs:
            dirs.append(extra)
    orig = str(env.get("ld_library_path", "")).strip()
    if orig and orig not in dirs:
        dirs.append(orig)
    return ":".join(dirs)


def require_board_runtime(board: dict, env: dict, need_pyaxengine: bool = True) -> None:
    """板端运行依赖硬检查：缺 ax_run_model / pyaxengine 时报可执行提示。"""
    missing = []
    if not env.get("ax_run_model"):
        missing.append(
            "ax_run_model 未找到（期望 /opt/bin/ax_run_model 或 PATH 中）——"
            "请安装 axengine 板端运行包"
        )
    if need_pyaxengine and not env.get("pyaxengine"):
        missing.append(
            "python3 无法 import axengine（pyaxengine 未安装）——"
            f"请先在板端执行: pip3 install pyaxengine"
            f"（探测详情: {env.get('pyaxengine_error', '')}）"
        )
    if missing:
        raise RuntimeError(
            f"板端 {env.get('host', board.get('host'))} 运行环境缺失: " + "; ".join(missing)
        )


# ─── 板端独占租约（多人/多任务共用板子时的防抢占、防误清） ───

def _lease_token(owner: str) -> str:
    """生成板端租约 token：owner-<pid>-<随机>，全程唯一。"""
    import socket, uuid
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", owner)[:40]
    return f"{safe}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def board_workdir(lease: BoardLease, name: str) -> str:
    """租约命名空间下的工作目录（所有上板临时文件都放这里）。"""
    return f"{lease.work_root}/{name}"


BOARD_LEASE_LOCK = f"{BOARD_LEASE_ROOT}/lock"


def list_board_leases(board: dict) -> dict[str, dict]:
    """列出板端租约根目录下所有 token 及 lease.json 信息。"""
    out = ssh(board, (
        f"mkdir -p {BOARD_LEASE_ROOT}; "
        f"for d in {BOARD_LEASE_ROOT}/*/; do "
        "[ -f \"$d/lease.json\" ] || continue; "
        "echo \"$(basename \"$d\")\\t$(cat \"$d/lease.json\")\"; done"
    ), timeout=30, max_tail=400)
    leases: dict[str, dict] = {}
    for line in out.splitlines():
        if "\t" not in line:
            continue
        tok, _, info = line.partition("\t")
        try:
            leases[tok] = json.loads(info)
        except Exception:
            leases[tok] = {}
    return leases


def cleanup_expired_leases(board: dict, ttl_min: int) -> None:
    """清理板端过期租约：只删租约根目录下 mtime 超过 TTL 的 token 目录。"""
    ssh(board, (
        f"mkdir -p {BOARD_LEASE_ROOT}; "
        f"find {BOARD_LEASE_ROOT} -mindepth 1 -maxdepth 1 -type d "
        f"-mmin +{ttl_min} -exec rm -rf {{}} +"
    ), timeout=60)


def board_lease_report(board: dict,
                       ttl_min: int = DEFAULT_LEASE_TTL // 60) -> list[dict]:
    """板端租约体检：返回每个 token 的归属与存活状态（只读，不删除）。

    供新任务判断"该不该清"：expired=True 表示 mtime 超过 TTL 的残留，
    可安全调用 cleanup_expired_leases() 清理；活租约会随心跳保持 mtime 新鲜。
    """
    import time
    leases = list_board_leases(board)
    out = ssh(board, (
        f"for d in {BOARD_LEASE_ROOT}/*/; do "
        "[ -f \"$d/lease.json\" ] || continue; "
        "echo \"$(basename \"$d\")\\t$(stat -c %Y \"$d\" 2>/dev/null || echo 0)\"; done"
    ), timeout=30, max_tail=400)
    mtimes: dict[str, int] = {}
    for line in out.splitlines():
        tok, _, m = line.partition("\t")
        try:
            mtimes[tok] = int(m)
        except ValueError:
            pass
    now = int(time.time())
    report: list[dict] = []
    for tok, info in leases.items():
        age_min = None
        if tok in mtimes:
            age_min = max(0, (now - mtimes[tok]) // 60)
        report.append({
            "token": tok,
            "owner": info.get("owner", "?"),
            "note": info.get("note", ""),
            "age_min": age_min,
            "expired": age_min is not None and age_min > ttl_min,
        })
    report.sort(key=lambda d: (d["age_min"] or 0), reverse=True)
    return report


def _read_lock_info(board: dict) -> dict:
    """读取当前锁持有者信息（无锁/损坏返回空 dict）。"""
    out = ssh(board, f"cat {BOARD_LEASE_LOCK}/lease.json 2>/dev/null",
              timeout=30, max_tail=200)
    # stderr 可能与输出合并（如首次连接的 host key 提示），只解析 JSON 部分
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def acquire_board_lease(board: dict, *, owner: str | None = None,
                        ttl: int = DEFAULT_LEASE_TTL, wait_seconds: int = 0,
                        note: str = "") -> BoardLease:
    """申请板端独占租约（固定锁名 ``/tmp/magnetar-lease/lock`` 原子 mkdir 抢锁）。

    - 成功：返回 BoardLease，租约目录 mtime 即心跳；
    - 被占用：清理过期租约后仍有人占用则抛 BoardBusyError（带占用者信息），
      不会动任何人的临时文件；
    - 工作目录命名空间 /tmp/magnetar-lease/<token>/，release 只删自己的 token 目录
      与仍由自己持有的锁。
    """
    import socket, time
    owner = owner or f"{socket.gethostname()}:{os.getpid()}"
    token = _lease_token(owner)
    work_root = f"{BOARD_LEASE_ROOT}/{token}"
    info = {
        "token": token, "owner": owner, "host": socket.gethostname(), "pid": os.getpid(),
        "note": note, "ttl": ttl,
    }
    ttl_min = max(1, ttl // 60)
    deadline = time.time() + max(0, wait_seconds)
    ssh(board, f"mkdir -p {BOARD_LEASE_ROOT}", timeout=30)
    # 无条件先扫一遍过期租约：新任务到来时崩溃残留自动清掉，活租约不受影响
    # （mtime 心跳；扫尾失败不阻塞获取，锁冲突路径上还会再扫）
    try:
        cleanup_expired_leases(board, ttl_min)
    except RuntimeError:
        pass
    while True:
        try:
            ssh(board, f"mkdir {BOARD_LEASE_LOCK}", timeout=30)
            break
        except RuntimeError:
            cleanup_expired_leases(board, ttl_min)
            lock_info = _read_lock_info(board)
            if lock_info:
                if time.time() < deadline:
                    time.sleep(5)
                    continue
                raise BoardBusyError(
                    f"板子 {board['host']} 正被占用: "
                    f"{lock_info.get('owner', '?')}（{lock_info.get('note') or '上板任务'}）" +
                    "。请等对方结束后重试，或用 MAGNETAR_BOARD 指定其他板子"
                )
            time.sleep(1)  # 偶发冲突重试
    ssh(board, (
        f"mkdir -p {BOARD_LEASE_LOCK}; "
        f"cat > {BOARD_LEASE_LOCK}/lease.json <<'EOF'\n"
        f"{json.dumps(info, ensure_ascii=False)}\nEOF"
    ), timeout=30)
    return BoardLease(board=board, token=token, dir=BOARD_LEASE_LOCK,
                      work_root=work_root, owner=owner, ttl=ttl)


def renew_board_lease(lease: BoardLease) -> None:
    """续租：touch 锁目录（更新 mtime 心跳）。"""
    ssh(lease.board, f"touch {BOARD_LEASE_LOCK}", timeout=30)


def release_board_lease(lease: BoardLease) -> None:
    """释放租约：只删自己的工作目录，以及仍由自己持有的锁。"""
    try:
        ssh(lease.board, (
            f"grep -qF '{lease.token}' {BOARD_LEASE_LOCK}/lease.json 2>/dev/null "
            f"&& rm -rf {BOARD_LEASE_LOCK}"
        ), timeout=30)
    except RuntimeError:
        pass
    try:
        ssh(lease.board, f"rm -rf {lease.work_root}", timeout=30)
    except RuntimeError:
        pass


@contextmanager
def board_lease(board: dict, *, owner: str | None = None,
                ttl: int = DEFAULT_LEASE_TTL, wait_seconds: int = 0,
                note: str = ""):
    """板端租约上下文管理器：退出时自动释放（含异常路径）。"""
    lease = acquire_board_lease(board, owner=owner, ttl=ttl,
                                wait_seconds=wait_seconds, note=note)
    try:
        yield lease
    finally:
        release_board_lease(lease)


def _is_valid_zip(path: Path) -> bool:
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except Exception:
        return False


def _download_axinferelease(url: str, dst: Path, timeout: int = 600) -> None:
    """下载 ax-remote-infer release zip（带重试），失败抛错。"""
    tmp = dst.with_suffix(".part")
    for attempt in range(3):
        proc = subprocess.run(
            ["curl", "-fsSL", "--retry", "2", "--connect-timeout", "15", "-o", str(tmp), url],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout,
        )
        if proc.returncode == 0 and _is_valid_zip(tmp):
            tmp.rename(dst)
            return
        print(f"[board_util] release 下载失败（attempt {attempt + 1}/3）: {proc.stdout[-300:]}")
        tmp.unlink(missing_ok=True)
    raise RuntimeError(f"ax-remote-infer release 下载失败: {url}")


def _default_scan_subnet() -> str | None:
    """默认扫描网段：MAGNETAR_SCAN_SUBNET 优先，否则取 dashboard 主机所在 /24。"""
    subnet = os.environ.get("MAGNETAR_SCAN_SUBNET")
    if subnet:
        return subnet
    try:
        host = urllib.parse.urlparse(DASHBOARD).hostname
    except Exception:
        return None
    if host and host.count(".") == 3:
        return ".".join(host.split(".")[:3]) + ".0/24"
    return None


def _scan_subnet_for_boards(subnet: str | None, target_hw: str, pwd: str) -> dict | None:
    """扫网段 18500 端口发现装了 ax_remote_infer 的板子，SSH 校验芯片型号后返回第一块匹配板。"""
    if not subnet:
        return None
    import concurrent.futures
    import ipaddress
    import socket
    try:
        net = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return None
    if net.version != 4:
        return None
    hosts = [str(ip) for ip in net.hosts()]
    if len(hosts) > 1024:
        print(f"[board_util] 扫描网段过大，仅扫描前 1024 个地址: {subnet}")
        hosts = hosts[:1024]
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        for ip, ok in zip(hosts, ex.map(lambda ip: port_open(ip, REMOTE_INFER_PORT, 1.0), hosts)):
            if ok:
                found.append(ip)
    for ip in sorted(found, key=lambda s: socket.inet_aton(s)):
        b = {"user": "root", "host": ip, "port": 22, "password": pwd}
        try:
            ct = ssh(b, "cat /proc/ax_proc/chip_type 2>/dev/null || hostname", 20).strip()
        except Exception:
            continue
        if target_hw.lower() in ct.lower():
            b["chip_type"] = ct
            return b
    return None
