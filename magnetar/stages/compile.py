"""COMPILE: Pulsar2 编译 ONNX → AXMODEL。

从 model_meta.json + input_dtype 参数动态构建配置，
src_dtype 严格对齐 Pulsar2 common.proto DataType 枚举。
"""
import json
from pathlib import Path


def _build_config(task_dir: Path, target_hw: str, pulsar_image: str,
                  input_dtype: str = "FP32") -> dict:
    """从 model_meta.json 构建 Pulsar2 编译配置。

    Args:
        input_dtype: Pulsar2 proto DataType 名 (FP32/U8/S8/FP16...)，决定 src_dtype 和预处理。
                     不绑定 model_meta 的 dtype——模型 ONNX 输入始终 FP32，
                     但 Pulsar2 input_processor 可做 U8→FP32 转换。
    """
    from magnetar.docker_util import get_pulsar2_proto_enums_cached

    meta = json.loads((task_dir / "export" / "model_meta.json").read_text(encoding="utf-8"))
    enums = get_pulsar2_proto_enums_cached(pulsar_image)
    dt = enums["DataType"]

    if input_dtype not in dt:
        raise ValueError(f"input_dtype '{input_dtype}' 不在 Pulsar2 DataType 枚举中。可用: {list(dt.keys())}")

    input_info = meta["inputs"][0]
    input_name = input_info["name"]
    input_shape = input_info["shape"]
    input_layout = input_info.get("layout", "NCHW")

    shape_str = "x".join(str(d) for d in input_shape)
    input_shapes = f"{input_name}:{shape_str}"

    # U8 输入 → /255 归一化；FP32 输入 → 不做处理
    if input_dtype == "U8":
        mean, std = [0, 0, 0], [255, 255, 255]
        calib_format = "Numpy"   # uint8 .npy
    elif input_dtype == "FP32":
        mean, std = [], []
        calib_format = "Numpy"
    else:
        mean, std = [], []
        calib_format = "Numpy"

    return {
        "input": "/workspace/export/model.onnx",
        "output_dir": "/workspace/compile",
        "output_name": "model.axmodel",
        "work_dir": "/workspace/compile/work",
        "model_type": "ONNX",
        "target_hardware": target_hw,
        "npu_mode": "NPU1",
        "input_shapes": input_shapes,
        "onnx_opt": {
            "disable_onnx_optimization": False,
            "enable_onnxsim": False,
            "model_check": True,
        },
        "quant": {
            "input_configs": [{
                "tensor_name": input_name,
                "calibration_dataset": "/workspace/export/calib_data/input.tar.gz",
                "calibration_format": calib_format,
                "calibration_size": 4,
                "calibration_mean": [],
                "calibration_std": [],
            }],
            "calibration_method": "MinMax",
            "precision_analysis": False,
            "highest_mix_precision": False,
        },
        "input_processors": [{
            "tensor_name": input_name,
            "tensor_format": "RGB",
            "tensor_layout": input_layout,
            "src_format": "RGB",
            "src_layout": input_layout,
            "src_dtype": input_dtype,
            "mean": mean,
            "std": std,
        }],
    }


def run(task_dir: Path, target_hw: str, pulsar_image: str,
        input_dtype: str = "FP32") -> None:
    from magnetar.docker_util import docker_pulsar2

    compile_dir = task_dir / "compile"
    compile_dir.mkdir(parents=True, exist_ok=True)

    config = _build_config(task_dir, target_hw, pulsar_image, input_dtype)
    config_path = compile_dir / "pulsar2_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[COMPILE] input_dtype={input_dtype}  input_shapes={config['input_shapes']}")

    log = docker_pulsar2(
        pulsar_image, str(task_dir.resolve()),
        "pulsar2 build --config /workspace/compile/pulsar2_config.json",
        timeout=3600,
    )
    (compile_dir / "compile.log").write_text(log, encoding="utf-8")

    axmodel = compile_dir / "model.axmodel"
    if not axmodel.is_file():
        raise RuntimeError(f"Pulsar2 未生成 {axmodel}")

    size_kb = axmodel.stat().st_size / 1024
    (compile_dir / "compile_report.md").write_text(
        f"# Compile Report\n\n"
        f"- image: {pulsar_image}\n"
        f"- target: {target_hw}\n"
        f"- input: {config['input_shapes']}\n"
        f"- src_dtype: {input_dtype}\n"
        f"- size: {size_kb:.1f} KB\n",
        encoding="utf-8",
    )
    print(f"[COMPILE] Done. model.axmodel = {size_kb:.1f} KB")
