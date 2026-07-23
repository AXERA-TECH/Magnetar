"""EXPORT: 导出静态 ONNX 并验证。"""
import json, tarfile
from pathlib import Path
import numpy as np

def run_mobilenet(task_dir: Path, sample: np.ndarray | None = None) -> np.ndarray:
    import onnx, onnxruntime as ort, torch
    from torchvision.models import MobileNet_V2_Weights, mobilenet_v2
    ed = task_dir / "export"; ed.mkdir(parents=True, exist_ok=True)
    model = mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT).eval()
    if sample is None: sample = np.random.rand(1, 3, 224, 224).astype(np.float32)
    st = torch.from_numpy(sample)
    with torch.no_grad(): to = model(st).detach().cpu().numpy()
    np.save(ed / "source_output.npy", to.astype(np.float32))
    np.save(ed / "sample_input.npy", sample.astype(np.float32))
    torch.onnx.export(model, st, ed / "model.onnx", input_names=["input"], output_names=["logits"], opset_version=17, dynamo=False)
    onnx.checker.check_model(onnx.load(ed / "model.onnx"))
    sess = ort.InferenceSession(str(ed / "model.onnx"), providers=["CPUExecutionProvider"])
    oo = sess.run(None, {"input": sample})[0].astype(np.float32)
    from magnetar.stages.simulate import cosine
    cos = cosine(to, oo)
    meta = {"model_name": "mobilenet_v2", "framework": "torchvision",
            "inputs": [{"name": "input", "shape": [1,3,224,224], "dtype": "float32", "layout": "NCHW"}],
            "outputs": [{"name": "logits", "shape": [1,1000], "dtype": "float32"}],
            "opset": 17, "torch_onnx_cosine": cos}
    (ed / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    ci = ed / "calib_data" / "input"; ci.mkdir(parents=True, exist_ok=True)
    for idx in range(4):
        np.save(ci / f"{idx:04d}.npy", np.clip(sample + (idx*0.01), 0, 1).astype(np.float32))
    tp = ed / "calib_data" / "input.tar.gz"
    with tarfile.open(tp, "w:gz") as tar:
        for npy in sorted(ci.glob("*.npy")): tar.add(npy, arcname=npy.name)
    (ed / "export_report.md").write_text(f"# Export Report\n\n- ONNX: model.onnx\n- Torch-ONNX cosine: {cos}\n", encoding="utf-8")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f: f.write(f"\n- EXPORT: model.onnx\n")
    return sample

def run_custom(task_dir: Path, onnx_path: str | Path):
    import shutil
    ed = task_dir / "export"; ed.mkdir(parents=True, exist_ok=True)
    shutil.copy2(onnx_path, ed / "model.onnx")
