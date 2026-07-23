"""COMPILE: Pulsar2 编译 ONNX → AXMODEL。"""
import json
from pathlib import Path


def _build_config(task_dir: Path, target_hardware: str) -> dict:
    """生成 Pulsar2 编译配置。"""
    return {
        "input": "/workspace/export/model.onnx",
        "output_dir": "/workspace/compile",
        "output_name": "model.axmodel",
        "work_dir": "/workspace/compile/work",
        "model_type": "ONNX",
        "target_hardware": target_hardware,
        "npu_mode": "NPU1",
        "input_shapes": "input:1x3x224x224",
        "onnx_opt": {
            "disable_onnx_optimization": False,
            "enable_onnxsim": False,
            "model_check": True,
        },
        "quant": {
            "input_configs": [{
                "tensor_name": "input",
                "calibration_dataset": "/workspace/export/calib_data/input.tar.gz",
                "calibration_format": "Numpy",
                "calibration_size": 4,
                "calibration_mean": [],
                "calibration_std": [],
            }],
            "calibration_method": "MinMax",
            "precision_analysis": False,
            "highest_mix_precision": False,
        },
        "input_processors": [{
            "tensor_name": "input",
            "tensor_format": "RGB",
            "tensor_layout": "NCHW",
            "src_format": "RGB",
            "src_layout": "NCHW",
            "src_dtype": "FP32",
            "mean": [],
            "std": [],
        }],
    }


def run(task_dir: Path, target_hardware: str, pulsar_image: str) -> None:
    """执行 Pulsar2 编译，产出 model.axmodel。"""
    from magnetar.docker_util import docker_pulsar2

    config = _build_config(task_dir, target_hardware)
    config_path = task_dir / "compile" / "pulsar2_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    log = docker_pulsar2(
        pulsar_image, str(task_dir),
        "pulsar2 build --config /workspace/compile/pulsar2_config.json",
        timeout=1800,
    )
    (task_dir / "compile" / "compile.log").write_text(log, encoding="utf-8")

    axmodel = task_dir / "compile" / "model.axmodel"
    if not axmodel.is_file():
        raise RuntimeError(f"Pulsar2 did not produce {axmodel}")

    (task_dir / "compile" / "compile_report.md").write_text(
        f"# Compile Report\n\n- image: {pulsar_image}\n- axmodel: {axmodel}\n"
        f"- size: {axmodel.stat().st_size / 1024:.1f} KB\n", encoding="utf-8")


def run_with_config(task_dir: Path, pulsar_image: str, config: dict) -> None:
    """使用自定义配置执行编译。"""
    from magnetar.docker_util import docker_pulsar2

    config_path = task_dir / "compile" / "pulsar2_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    log = docker_pulsar2(
        pulsar_image, str(task_dir),
        "pulsar2 build --config /workspace/compile/pulsar2_config.json",
        timeout=1800,
    )
    (task_dir / "compile" / "compile.log").write_text(log, encoding="utf-8")

    axmodel = task_dir / "compile" / "model.axmodel"
    if not axmodel.is_file():
        raise RuntimeError(f"Pulsar2 did not produce {axmodel}")
