"""RUNONBOARD: 板端部署和验证。返回 metrics dict，无板子返回 None。"""
import json, os, re, shutil
from pathlib import Path
import numpy as np

def run(task_dir: Path, sample: np.ndarray, target_hw: str, pwd: str, cpp_binary: Path | None = None) -> dict | None:
    from magnetar.board_util import ensure_remote_infer, select_board, ssh, scp_to, scp_from
    board = select_board(target_hw, pwd)
    if board is None:
        from magnetar.stages.state import mark_stage
        mark_stage(task_dir, "RUNONBOARD", status="skipped", summary="BOARD 未配置，自动跳过")
        return None
    # 上板先确保 ax_remote_infer daemon 已装（18500 不通则静默安装），装后可扫端口发现板子
    try:
        ensure_remote_infer(board)
    except Exception as e:
        print(f"[RUNONBOARD] ensure_remote_infer 失败（忽略，继续上板）: {e}")
    rb = task_dir / "runonboard"; rb.mkdir(parents=True, exist_ok=True)
    in_npy = rb / "input.npy"; in_bin = rb / "input.bin"
    np.save(in_npy, sample.astype(np.float32)); sample.astype(np.float32).tofile(in_bin)
    rd = f"/tmp/magnetar_{os.getpid()}"
    ssh(board, f"rm -rf {rd} && mkdir -p {rd}")
    scp_to(board, task_dir / "package", f"{rd}/package")
    scp_to(board, in_npy, f"{rd}/input.npy"); scp_to(board, in_bin, f"{rd}/input.bin")
    # 按 model_meta 找通用 SDK 入口；找不到回退 legacy mobilenet_sdk
    pkg_name = "mobilenet_sdk"
    try:
        meta = json.loads((task_dir / "package" / "models" / "model_meta.json").read_text(encoding="utf-8"))
        import re
        pkg_name = re.sub(r"[^0-9a-zA-Z_]", "_", str(meta.get("model_name", "model")).lower()) + "_sdk"
    except Exception:
        pass
    sdk_entry = f"package/python/{pkg_name}/example.py"
    if not (task_dir / "package" / "python" / pkg_name / "example.py").is_file():
        sdk_entry = "package/python/mobilenet_sdk/example.py"
    py_log = ssh(board, f"cd {rd} && LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/package/python python3 {sdk_entry} --model package/models/model.axmodel --input input.npy --output-dir py_out", timeout=240)
    cpp_log = ""
    if cpp_binary and cpp_binary.exists():
        scp_to(board, cpp_binary, f"{rd}/mobilenet_example")
        ssh(board, f"chmod +x {rd}/mobilenet_example")
        cpp_log = ssh(board, f"cd {rd} && LD_LIBRARY_PATH=/soc/lib ./mobilenet_example package/models/model.axmodel input.bin cpp_out && ls cpp_out", timeout=240)
    scp_from(board, f"{rd}/py_out", rb / "py_out")
    py_outputs = sorted((rb / "py_out").glob("output_*.npy"))
    if not py_outputs:
        # legacy：单输出直接落盘 python_output.npy
        scp_from(board, f"{rd}/python_output.npy", rb / "python_output.npy")
        po = np.load(rb / "python_output.npy").astype(np.float32)
    else:
        po = np.load(py_outputs[0]).astype(np.float32)
    from magnetar.stages.simulate import cosine
    m = {"board": board["host"], "chip_type": board["chip_type"], "python_shape": list(po.shape)}
    if cpp_binary and cpp_binary.exists():
        scp_from(board, f"{rd}/cpp_out", rb / "cpp_out")
        cpp_bins = sorted((rb / "cpp_out").glob("output_*.bin"))
        co = np.fromfile(cpp_bins[0], dtype=np.float32).reshape(po.shape) if cpp_bins else po
        m["cpp_shape"] = list(co.shape); m["python_cpp_cosine"] = cosine(po, co)
        m["python_cpp_mae"] = float(np.mean(np.abs(po - co)))
    (rb / "runonboard_report.md").write_text("# Run On Board Report\n\n"+"\n".join(f"- {k}: {v}" for k,v in m.items())+f"\n\n## Python Log\n```\n{py_log[-4000:]}\n```\n\n## C++ Log\n```\n{cpp_log[-4000:]}\n```", encoding="utf-8")
    shutil.copy2(rb / "runonboard_report.md", task_dir / "package" / "reports" / "runonboard_report.md")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "RUNONBOARD", metrics=m, summary=f"板端 {board['host']} {board['chip_type']}")
    return m
