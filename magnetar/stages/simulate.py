"""SIMULATE: ONNX vs AXMODEL 精度对分。"""
import json
from pathlib import Path

import numpy as np


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float32).reshape(-1)
    b = b.astype(np.float32).reshape(-1)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def run(task_dir: Path, sample: np.ndarray, pulsar_image: str,
        input_name: str = "input", output_name: str = "logits") -> dict:
    """运行 Pulsar2 仿真并对比 ONNX 输出。"""
    from magnetar.docker_util import docker_pulsar2
    import onnxruntime as ort

    sim_dir = task_dir / "simulate"
    input_dir = sim_dir / "input"
    output_dir = sim_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    sample.astype(np.float32).tofile(input_dir / "input.bin")

    log = docker_pulsar2(
        pulsar_image, str(task_dir),
        "pulsar2 run --model /workspace/compile/model.axmodel "
        "--input_dir /workspace/simulate/input --output_dir /workspace/simulate/output",
        timeout=900,
    )
    (sim_dir / "pulsar2_run.log").write_text(log, encoding="utf-8")

    sess = ort.InferenceSession(
        str(task_dir / "export" / "model.onnx"), providers=["CPUExecutionProvider"])
    onnx_output = sess.run(None, {input_name: sample})[0].astype(np.float32)

    bin_path = output_dir / f"{output_name}.bin"
    ax_output = np.fromfile(bin_path, dtype=np.float32).reshape(onnx_output.shape)

    metrics = {
        "cosine_similarity": cosine(onnx_output, ax_output),
        "mae": float(np.mean(np.abs(onnx_output - ax_output))),
        "max_abs_diff": float(np.max(np.abs(onnx_output - ax_output))),
    }
    (sim_dir / "simulate_report.md").write_text(
        "# Simulate Report\n\n" + "\n".join(f"- {k}: {v}" for k, v in metrics.items()),
        encoding="utf-8")
    (sim_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics
