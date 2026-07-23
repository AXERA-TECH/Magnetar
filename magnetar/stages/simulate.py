"""SIMULATE: ONNX vs AXMODEL 精度对分。

优先板端 ax_run_model（秒级），不可用时回退 pulsar2 run（分钟级）。
"""
import json, os
from pathlib import Path
import numpy as np

def cosine(a, b):
    a, b = a.astype(np.float32).reshape(-1), b.astype(np.float32).reshape(-1)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

def run(task_dir: Path, sample: np.ndarray, pulsar_image: str,
        input_name="input", output_name="logits",
        board: dict | None = None) -> dict:
    """SIMULATE 主入口：优先板端快速通道，不可用时回退 Pulsar2 仿真。"""
    sd = task_dir / "simulate"
    sd.mkdir(parents=True, exist_ok=True)

    # 1. 先算 ONNX 参考输出
    import onnxruntime as ort
    sess = ort.InferenceSession(str(task_dir / "export" / "model.onnx"), providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {input_name: sample})[0].astype(np.float32)

    # 2. 尝试板端快速通道
    if board is not None:
        try:
            metrics = _run_on_board(task_dir, sample, onnx_out, board, output_name)
            _write_report(sd, metrics, method=f"board: {board['host']}")
            return metrics
        except Exception as e:
            (sd / "board_fast_failed.log").write_text(str(e), encoding="utf-8")
            print(f"[SIMULATE] Board fast path failed: {e}, falling back to pulsar2 run")

    # 3. 回退 Pulsar2 仿真
    return _run_pulsar2(task_dir, sample, onnx_out, pulsar_image, sd, input_name, output_name)


def _run_on_board(task_dir: Path, sample: np.ndarray, onnx_out: np.ndarray,
                  board: dict, output_name: str) -> dict:
    """板端 ax_run_model 快速通道。"""
    from magnetar.board_util import ssh, scp_to, scp_from

    sd = task_dir / "simulate"
    remote = f"/tmp/magnetar_sim_{os.getpid()}"
    ssh(board, f"rm -rf {remote} && mkdir -p {remote}/input {remote}/output")

    # 上传模型和输入
    axmodel = task_dir / "compile" / "model.axmodel"
    scp_to(board, axmodel, f"{remote}/model.axmodel")

    input_dir = sd / "board_input"
    input_dir.mkdir(exist_ok=True)
    sample.astype(np.float32).tofile(input_dir / "input.bin")
    (input_dir / "input_list.txt").write_text("input.bin\n", encoding="utf-8")
    scp_to(board, input_dir, f"{remote}/input_dir")

    # 运行 ax_run_model
    ssh(board,
        f"cd {remote} && "
        f"/opt/bin/ax_run_model -m model.axmodel "
        f"-i input_dir -o output -l input_dir/input_list.txt -w 0 -r 1",
        timeout=120)

    # 下载结果
    scp_from(board, f"{remote}/output", sd / "board_output")

    # 读取 ax_run_model 输出
    output_dir = sd / "board_output"
    bin_files = sorted(output_dir.glob("*.bin"))
    if not bin_files:
        raise RuntimeError("ax_run_model produced no output")

    ax_out = np.fromfile(bin_files[0], dtype=np.float32).reshape(onnx_out.shape)

    return {
        "cosine_similarity": cosine(onnx_out, ax_out),
        "mae": float(np.mean(np.abs(onnx_out - ax_out))),
        "max_abs_diff": float(np.max(np.abs(onnx_out - ax_out))),
    }


def _run_pulsar2(task_dir: Path, sample: np.ndarray, onnx_out: np.ndarray,
                 pulsar_image: str, sd: Path, input_name: str, output_name: str) -> dict:
    """Pulsar2 Docker 仿真（慢速回退）。"""
    from magnetar.docker_util import docker_pulsar2
    ind = sd / "input"; outd = sd / "output"
    ind.mkdir(parents=True, exist_ok=True); outd.mkdir(parents=True, exist_ok=True)
    sample.astype(np.float32).tofile(ind / f"{input_name}.bin")
    log = docker_pulsar2(pulsar_image, str(task_dir.resolve()),
        "pulsar2 run --model /workspace/compile/model.axmodel "
        "--input_dir /workspace/simulate/input --output_dir /workspace/simulate/output",
        timeout=900)
    (sd / "pulsar2_run.log").write_text(log, encoding="utf-8")
    ax_out = np.fromfile(outd / f"{output_name}.bin", dtype=np.float32).reshape(onnx_out.shape)
    metrics = {
        "cosine_similarity": cosine(onnx_out, ax_out),
        "mae": float(np.mean(np.abs(onnx_out - ax_out))),
        "max_abs_diff": float(np.max(np.abs(onnx_out - ax_out))),
    }
    _write_report(sd, metrics, method="pulsar2 run")
    return metrics


def _write_report(sd: Path, metrics: dict, method: str):
    (sd / "simulate_report.md").write_text(
        f"# Simulate Report\n\nMethod: {method}\n\n" +
        "\n".join(f"- {k}: {v}" for k, v in metrics.items()),
        encoding="utf-8")
    (sd / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
