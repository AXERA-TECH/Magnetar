"""EXPORT: 导出静态 ONNX 并验证。"""
import json
import tarfile
from pathlib import Path

import numpy as np


def run_mobilenet(task_dir: Path, sample: np.ndarray | None = None) -> np.ndarray:
    """MobileNetV2 特化：下载权重、导出 ONNX、验证、生成校准数据。"""
    import onnx
    import onnxruntime as ort
    import torch
    from torchvision.models import MobileNet_V2_Weights, mobilenet_v2

    export_dir = task_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    weights = MobileNet_V2_Weights.DEFAULT
    model = mobilenet_v2(weights=weights).eval()

    if sample is None:
        sample = np.random.rand(1, 3, 224, 224).astype(np.float32)
    sample_tensor = torch.from_numpy(sample)

    with torch.no_grad():
        torch_output = model(sample_tensor).detach().cpu().numpy()
    np.save(export_dir / "source_output.npy", torch_output.astype(np.float32))
    np.save(export_dir / "sample_input.npy", sample.astype(np.float32))

    onnx_path = export_dir / "model.onnx"
    torch.onnx.export(
        model, sample_tensor, onnx_path,
        input_names=["input"], output_names=["logits"],
        opset_version=17, dynamo=False,
    )

    # 验证 ONNX
    onnx_model = onnx.load(onnx_path)
    onnx.checker.check_model(onnx_model)
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    onnx_output = sess.run(None, {"input": sample})[0].astype(np.float32)

    from magnetar.stages.simulate import cosine
    cos = cosine(torch_output, onnx_output)

    meta = {
        "model_name": "mobilenet_v2",
        "framework": "torchvision",
        "inputs": [{"name": "input", "shape": [1, 3, 224, 224], "dtype": "float32", "layout": "NCHW"}],
        "outputs": [{"name": "logits", "shape": [1, 1000], "dtype": "float32"}],
        "opset": 17,
        "torch_onnx_cosine": cos,
    }
    (export_dir / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # 校准数据
    calib_input = export_dir / "calib_data" / "input"
    calib_input.mkdir(parents=True, exist_ok=True)
    for idx in range(4):
        data = np.clip(sample + (idx * 0.01), 0, 1).astype(np.float32)
        np.save(calib_input / f"{idx:04d}.npy", data)
    tar_path = export_dir / "calib_data" / "input.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for npy in sorted(calib_input.glob("*.npy")):
            tar.add(npy, arcname=npy.name)

    (export_dir / "export_report.md").write_text(
        f"# Export Report\n\n- ONNX: {onnx_path}\n- Torch-ONNX cosine: {cos}\n", encoding="utf-8")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"\n- EXPORT: {onnx_path}\n")

    return sample


def run_from_onnx(task_dir: Path, onnx_source: str | Path) -> None:
    """从已有 ONNX 文件初始化 EXPORT 阶段。"""
    import shutil
    export_dir = task_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(onnx_source, export_dir / "model.onnx")
