"""EXPORT: 导出静态 ONNX 并验证。

非 MobileNet 模型统一走 ``run_generic``：先尝试最简单导出，失败自动降级，
详见 ``magnetar/export_onnx.py``。
"""
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


def run_generic(task_dir: Path, *, model=None, example_inputs=None, load_script=None,
                arch=None, checkpoint=None, input_names=None, output_names=None,
                opset=17, model_name="model", sample_variants=4, calibration_data=None,
                cosine_threshold=0.99,
                require_static=True) -> dict:
    """EXPORT 通用编排入口：任意 PyTorch 模型 -> 静态 ONNX + meta + 校准数据。

    支持三种模型来源（互斥）：已加载的 ``model`` 对象、``load_script``（最普适）、
    ``arch``（torchvision/timm/hf 架构名，可配 ``checkpoint`` 权重）。
    ``calibration_data``：真实业务校准数据（目录或样本列表），优先于扰动兜底序列。
    返回 dict: onnx_path / model_meta / attempts / cosine / input_names / output_names。
    全部路径失败时抛 ExportError（诊断报告在 export/export_report.md）。
    """
    from magnetar.export_onnx import export_to_onnx
    return export_to_onnx(
        task_dir,
        model=model,
        example_inputs=example_inputs,
        load_script=load_script,
        arch=arch,
        checkpoint=checkpoint,
        input_names=input_names,
        output_names=output_names,
        opset=opset,
        model_name=model_name,
        sample_variants=sample_variants,
        calibration_data=calibration_data,
        cosine_threshold=cosine_threshold,
        require_static=require_static,
    )
