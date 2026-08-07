"""AX 板端 SSH/SCP/daemon 工具函数。

上板前用 ensure_remote_infer() 确保 ax_remote_infer daemon 已装并监听 18500，
装好后即可通过扫描 18500 端口发现板子（select_board 在 dashboard 不可用时回退端口扫描）。
"""
import json, os, subprocess, urllib.parse, urllib.request
from pathlib import Path

DASHBOARD = os.environ.get("MAGNETAR_BOARD_DASHBOARD", "http://10.126.35.22:25000/api/devices")
REMOTE_INFER_PORT = 18500
AX_REMOTE_INFER_URL = os.environ.get(
    "AX_REMOTE_INFER_URL",
    "https://github.com/AXERA-TECH/ax-remote-infer/releases/download/latest/ax-remote-infer-latest.zip",
)

def _ssh_base(b): return ["sshpass", "-p", b["password"], "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10", "-p", str(b["port"]), f"{b['user']}@{b['host']}"]
def _scp_base(b): return ["sshpass", "-p", b["password"], "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-P", str(b["port"])]

def ssh(board: dict, cmd: str, timeout=120, max_tail=None) -> str:
    """远程执行命令；max_tail 指定时只返回尾部（大输出建议用，完整输出不回上下文）。"""
    proc = subprocess.run(_ssh_base(board) + [cmd], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
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

def scp_from(board: dict, src: str, dst: str | Path):
    from magnetar.docker_util import run as _r
    a = _scp_base(board)
    if src.endswith("include"): a.append("-r")
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
        _download_axinferelease(AX_REMOTE_INFER_URL, zip_path)
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
