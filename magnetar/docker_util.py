"""Docker/Pulsar2 工具函数。"""
import os
import re
import subprocess


def run(cmd, cwd=None, timeout=600):
    """执行命令，失败时抛出 RuntimeError。"""
    proc = subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=timeout, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {proc.returncode}): {' '.join(cmd)}\n{proc.stdout}"
        )
    return proc.stdout


def latest_pulsar2_image() -> str:
    """查找本地最新的 pulsar2 Docker 镜像。"""
    output = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=30)
    candidates = []
    for image in output.splitlines():
        repo, _, tag = image.partition(":")
        if repo != "pulsar2":
            continue
        match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:-|$)", tag)
        if not match:
            continue
        version = tuple(int(part or 0) for part in match.groups())
        candidates.append((version, image))
    if not candidates:
        raise RuntimeError("No local pulsar2:* Docker image found. Run: ./scripts/install_pulsar2.sh")
    return max(candidates, key=lambda item: item[0])[1]


def docker_pulsar2(image: str, workspace: str, command: str, timeout=1800) -> str:
    """在 Pulsar2 Docker 容器中执行命令。"""
    uid, gid = os.getuid(), os.getgid()
    wrapped = (
        "set +e; "
        f"PATH=/usr/local/bin/.venv/bin:/opt/pulsar2:$PATH {command}; "
        "status=$?; "
        f"chown -R {uid}:{gid} /workspace; "
        "exit $status"
    )
    return run(
        ["docker", "run", "--rm", "-v", f"{workspace}:/workspace", image, "-lc", wrapped],
        timeout=timeout,
    )


def make_writable(task_dir: str) -> None:
    """修复 Docker 产生的 root-owned 文件权限。"""
    from pathlib import Path
    if not Path(task_dir).exists():
        return
    image = latest_pulsar2_image()
    uid, gid = os.getuid(), os.getgid()
    run(
        ["docker", "run", "--rm", "-v", f"{task_dir}:/workspace", image,
         "-lc", f"chown -R {uid}:{gid} /workspace"],
        timeout=120,
    )
