"""RUNONBOARD: 板端部署和验证。返回 metrics dict，无板子返回 None。"""
import os, shutil
from pathlib import Path
import numpy as np

def run(task_dir: Path, sample: np.ndarray, target_hw: str, pwd: str, cpp_binary: Path | None = None) -> dict | None:
    from magnetar.board_util import select_board, ssh, scp_to, scp_from
    board = select_board(target_hw, pwd)
    if board is None: return None
    rb = task_dir / "runonboard"; rb.mkdir(parents=True, exist_ok=True)
    in_npy = rb / "input.npy"; in_bin = rb / "input.bin"
    np.save(in_npy, sample.astype(np.float32)); sample.astype(np.float32).tofile(in_bin)
    rd = f"/tmp/magnetar_{os.getpid()}"
    ssh(board, f"rm -rf {rd} && mkdir -p {rd}")
    scp_to(board, task_dir / "package", f"{rd}/package")
    scp_to(board, in_npy, f"{rd}/input.npy"); scp_to(board, in_bin, f"{rd}/input.bin")
    py_log = ssh(board, f"cd {rd} && LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/package/python python3 package/python/mobilenet_sdk/example.py --model package/models/model.axmodel --input input.npy --output python_output.npy", timeout=240)
    cpp_log = ""
    if cpp_binary and cpp_binary.exists():
        scp_to(board, cpp_binary, f"{rd}/mobilenet_example")
        ssh(board, f"chmod +x {rd}/mobilenet_example")
        cpp_log = ssh(board, f"cd {rd} && LD_LIBRARY_PATH=/soc/lib ./mobilenet_example package/models/model.axmodel input.bin cpp_output.bin package/cpp/imagenet_classes.txt", timeout=240)
    scp_from(board, f"{rd}/python_output.npy", rb / "python_output.npy")
    po = np.load(rb / "python_output.npy").astype(np.float32)
    from magnetar.stages.simulate import cosine
    m = {"board": board["host"], "chip_type": board["chip_type"], "python_shape": list(po.shape)}
    if cpp_binary and cpp_binary.exists():
        scp_from(board, f"{rd}/cpp_output.bin", rb / "cpp_output.bin")
        co = np.fromfile(rb / "cpp_output.bin", dtype=np.float32).reshape(po.shape)
        m["cpp_shape"] = list(co.shape); m["python_cpp_cosine"] = cosine(po, co)
        m["python_cpp_mae"] = float(np.mean(np.abs(po - co)))
    (rb / "runonboard_report.md").write_text("# Run On Board Report\n\n"+"\n".join(f"- {k}: {v}" for k,v in m.items())+f"\n\n## Python Log\n```\n{py_log[-4000:]}\n```\n\n## C++ Log\n```\n{cpp_log[-4000:]}\n```", encoding="utf-8")
    shutil.copy2(rb / "runonboard_report.md", task_dir / "package" / "reports" / "runonboard_report.md")
    return m
