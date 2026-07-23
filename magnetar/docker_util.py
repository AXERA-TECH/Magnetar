"""Docker/Pulsar2 工具函数。"""
import os, re, subprocess

def run(cmd, cwd=None, timeout=600):
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed (exit {proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return proc.stdout

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

def docker_pulsar2(image: str, workspace: str, command: str, timeout=1800) -> str:
    uid, gid = os.getuid(), os.getgid()
    wrapped = f"set +e; PATH=/usr/local/bin/.venv/bin:/opt/pulsar2:$PATH {command}; status=$?; chown -R {uid}:{gid} /workspace; exit $status"
    return run(["docker", "run", "--rm", "-v", f"{workspace}:/workspace", image, "-lc", wrapped], timeout=timeout)

def make_writable(task_dir: str):
    from pathlib import Path
    if not Path(task_dir).exists(): return
    img = latest_pulsar2_image()
    uid, gid = os.getuid(), os.getgid()
    run(["docker", "run", "--rm", "-v", f"{task_dir}:/workspace", img, "-lc", f"chown -R {uid}:{gid} /workspace"], timeout=120)
