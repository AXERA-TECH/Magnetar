"""AX 板端 SSH/SCP 工具函数。"""
import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


DASHBOARD_URL = os.environ.get(
    "MAGNETAR_BOARD_DASHBOARD", "http://10.126.35.22:25000/api/devices"
)


def _ssh_base(board: dict) -> list:
    return [
        "sshpass", "-p", board["password"],
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10", "-p", str(board["port"]),
        f"{board['user']}@{board['host']}",
    ]


def _scp_base(board: dict) -> list:
    return [
        "sshpass", "-p", board["password"],
        "scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-P", str(board["port"]),
    ]


def ssh(board: dict, command: str, timeout=120) -> str:
    """在板端执行命令，返回 stdout。"""
    proc = subprocess.run(
        _ssh_base(board) + [command],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Remote command failed (exit {proc.returncode}): {command}\n{proc.stdout}"
        )
    return proc.stdout


def scp_to(board: dict, source: str | Path, dest: str) -> None:
    """上传文件/目录到板端。"""
    from .docker_util import run as _run
    args = _scp_base(board)
    if Path(source).is_dir():
        args.append("-r")
    _run(args + [str(source), f"{board['user']}@{board['host']}:{dest}"], timeout=240)


def scp_from(board: dict, source: str, dest: str | Path) -> None:
    """从板端下载文件/目录。"""
    from .docker_util import run as _run
    args = _scp_base(board)
    if source.endswith("include"):
        args.append("-r")
    _run(args + [f"{board['user']}@{board['host']}:{source}", str(dest)], timeout=240)


def select_board(target_hardware: str, password: str = "123456") -> dict | None:
    """选择一块匹配的空闲 AX 板子。"""
    explicit = os.environ.get("MAGNETAR_BOARD")
    if explicit:
        parsed = urllib.parse.urlparse(
            explicit if "://" in explicit else f"ssh://{explicit}"
        )
        user = parsed.username or "root"
        host = parsed.hostname
        port = parsed.port or 22
        if not host:
            raise RuntimeError(f"Invalid MAGNETAR_BOARD: {explicit}")
        chip_type = ssh(
            {"user": user, "host": host, "port": port, "password": password},
            "cat /proc/ax_proc/chip_type 2>/dev/null || hostname", timeout=20,
        ).strip()
        if target_hardware.lower() not in chip_type.lower():
            raise RuntimeError(
                f"Board chip {chip_type!r} != TARGET_HARDWARE={target_hardware}"
            )
        return {"user": user, "host": host, "port": port, "password": password, "chip_type": chip_type}

    try:
        with urllib.request.urlopen(DASHBOARD_URL, timeout=10) as resp:
            payload = json.load(resp)
    except Exception:
        return None

    devices = payload.get("devices", payload if isinstance(payload, list) else [])
    for item in devices:
        chip_type = str(item.get("chip_type", ""))
        if target_hardware.lower() not in chip_type.lower():
            continue
        if item.get("is_occupied"):
            continue
        host = item.get("ip") or item.get("host")
        if not host:
            continue
        return {
            "user": item.get("default_user") or "root",
            "host": host,
            "port": int(item.get("ssh_port") or 22),
            "password": password,
            "chip_type": chip_type,
        }
    return None
