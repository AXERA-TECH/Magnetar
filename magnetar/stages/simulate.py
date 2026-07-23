"""SIMULATE: ONNX vs AXMODEL 精度对分。"""
import json
from pathlib import Path
import numpy as np

def cosine(a, b):
    a, b = a.astype(np.float32).reshape(-1), b.astype(np.float32).reshape(-1)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

def run(task_dir: Path, sample: np.ndarray, pulsar_image: str, input_name="input", output_name="logits") -> dict:
    from magnetar.docker_util import docker_pulsar2
    import onnxruntime as ort
    sd = task_dir / "simulate"; ind = sd / "input"; outd = sd / "output"
    ind.mkdir(parents=True, exist_ok=True); outd.mkdir(parents=True, exist_ok=True)
    sample.astype(np.float32).tofile(ind / "input.bin")
    log = docker_pulsar2(pulsar_image, str(task_dir),
        f"pulsar2 run --model /workspace/compile/model.axmodel --input_dir /workspace/simulate/input --output_dir /workspace/simulate/output", timeout=900)
    (sd / "pulsar2_run.log").write_text(log, encoding="utf-8")
    sess = ort.InferenceSession(str(task_dir / "export" / "model.onnx"), providers=["CPUExecutionProvider"])
    onnx_out = sess.run(None, {input_name: sample})[0].astype(np.float32)
    ax_out = np.fromfile(outd / f"{output_name}.bin", dtype=np.float32).reshape(onnx_out.shape)
    m = {"cosine_similarity": cosine(onnx_out, ax_out), "mae": float(np.mean(np.abs(onnx_out - ax_out))),
         "max_abs_diff": float(np.max(np.abs(onnx_out - ax_out)))}
    (sd / "simulate_report.md").write_text("# Simulate Report\n\n" + "\n".join(f"- {k}: {v}" for k,v in m.items()), encoding="utf-8")
    (sd / "metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    return m
