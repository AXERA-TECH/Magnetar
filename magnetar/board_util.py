"""AX 板端 SSH/SCP 工具函数。"""
import json, os, subprocess, urllib.parse, urllib.request
from pathlib import Path

DASHBOARD = os.environ.get("MAGNETAR_BOARD_DASHBOARD", "http://10.126.35.22:25000/api/devices")

def _ssh_base(b): return ["sshpass", "-p", b["password"], "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10", "-p", str(b["port"]), f"{b['user']}@{b['host']}"]
def _scp_base(b): return ["sshpass", "-p", b["password"], "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-P", str(b["port"])]

def ssh(board: dict, cmd: str, timeout=120) -> str:
    proc = subprocess.run(_ssh_base(board) + [cmd], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if proc.returncode != 0: raise RuntimeError(f"Remote failed (exit {proc.returncode}): {cmd}\n{proc.stdout}")
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
    return None
