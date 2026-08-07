"""SIMULATE: ONNX vs AXMODEL 精度对分。

有板必上板：优先板端 ax_run_model（秒级），找不到板或板端失败时才回退 pulsar2 run（分钟级）。
"""
import json, os
from pathlib import Path
import numpy as np

def cosine(a, b):
    a, b = a.astype(np.float32).reshape(-1), b.astype(np.float32).reshape(-1)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

def run(task_dir: Path, sample: np.ndarray, pulsar_image: str,
        input_name="input", output_name="logits",
        board: dict | None = None,
        target_hw: str | None = None, board_pwd: str = "123456") -> dict:
    """SIMULATE 主入口：有板优先板端快速通道，无板才回退 Pulsar2 仿真。

    board 为空且给定 target_hw 时，自动用 select_board() 找空闲板；
    找不到板或板端失败时回退 pulsar2 run。
    """
    sd = task_dir / "simulate"
    sd.mkdir(parents=True, exist_ok=True)

    # 1. 先算 ONNX 参考输出
    import onnxruntime as ort
    sess = ort.InferenceSession(str(task_dir / "export" / "model.onnx"), providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {input_name: sample})[0].astype(np.float32)

    # 2. 尝试板端快速通道：先按配置，未配置时自动找空闲板
    metrics = None
    if board is None and target_hw:
        try:
            from magnetar.board_util import select_board
            board = select_board(target_hw, board_pwd)
            if board is not None:
                print(f"[SIMULATE] Auto-selected board {board['host']} ({board.get('chip_type', '')})")
        except Exception as e:
            (sd / "board_select_failed.log").write_text(str(e), encoding="utf-8")
            print(f"[SIMULATE] Board selection failed: {e}, falling back to pulsar2 run")
    if board is not None:
        try:
            metrics = _run_on_board(task_dir, sample, onnx_out, board, output_name, input_name)
            _write_report(sd, metrics, method=f"board: {board['host']}")
        except Exception as e:
            (sd / "board_fast_failed.log").write_text(str(e), encoding="utf-8")
            print(f"[SIMULATE] Board fast path failed: {e}, falling back to pulsar2 run")

    # 3. 回退 Pulsar2 仿真
    if metrics is None:
        metrics = _run_pulsar2(task_dir, sample, onnx_out, pulsar_image, sd, input_name, output_name)

    from magnetar.stages.state import mark_stage
    mark_stage(
        task_dir, "SIMULATE",
        metrics={
            "cosine_similarity": metrics.get("cosine_similarity"),
            "mae": metrics.get("mae"),
            "max_abs_diff": metrics.get("max_abs_diff"),
        },
        summary=f"SIMULATE cosine={metrics.get('cosine_similarity', 'N/A')}",
    )
    return metrics


def _run_on_board(task_dir: Path, sample: np.ndarray, onnx_out: np.ndarray,
                  board: dict, output_name: str, input_name: str) -> dict:
    """板端 ax_run_model 快速通道。"""
    from magnetar.board_util import ensure_remote_infer, ssh, scp_to, scp_from
    from magnetar.io_format import read_ax_run_model_output, write_ax_run_model_input

    # 上板先确保 ax_remote_infer daemon 已装（18500 不通则静默安装），装后可扫端口发现板子
    try:
        ensure_remote_infer(board)
    except Exception as e:
        print(f"[SIMULATE] ensure_remote_infer 失败（忽略，继续上板）: {e}")

    sd = task_dir / "simulate"
    remote = f"/tmp/magnetar_sim_{os.getpid()}"
    ssh(board, f"rm -rf {remote} && mkdir -p {remote}/input {remote}/output")

    # 上传模型和输入
    axmodel = task_dir / "compile" / "model.axmodel"
    scp_to(board, axmodel, f"{remote}/model.axmodel")

    input_dir = sd / "board_input"
    input_dir.mkdir(exist_ok=True)
    write_ax_run_model_input(input_dir, input_name, sample)
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
    ax_out = read_ax_run_model_output(output_dir, onnx_out.shape)

    return {
        "cosine_similarity": cosine(onnx_out, ax_out),
        "mae": float(np.mean(np.abs(onnx_out - ax_out))),
        "max_abs_diff": float(np.max(np.abs(onnx_out - ax_out))),
    }


def _run_pulsar2(task_dir: Path, sample: np.ndarray, onnx_out: np.ndarray,
                 pulsar_image: str, sd: Path, input_name: str, output_name: str) -> dict:
    """Pulsar2 Docker 仿真（慢速回退）。"""
    from magnetar.docker_util import docker_pulsar2
    from magnetar.io_format import read_pulsar2_run_output, write_pulsar2_run_input
    ind = sd / "input"; outd = sd / "output"
    ind.mkdir(parents=True, exist_ok=True); outd.mkdir(parents=True, exist_ok=True)
    write_pulsar2_run_input(ind, input_name, sample)
    log = docker_pulsar2(pulsar_image, str(task_dir.resolve()),
        "pulsar2 run --model /workspace/compile/model.axmodel "
        "--input_dir /workspace/simulate/input --output_dir /workspace/simulate/output",
        timeout=900)
    (sd / "pulsar2_run.log").write_text(log, encoding="utf-8")
    ax_out = read_pulsar2_run_output(outd, output_name, onnx_out.shape)
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
