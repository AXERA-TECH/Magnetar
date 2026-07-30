"""COMPILE: Pulsar2 编译 ONNX → AXMODEL。

v2: 编译前自动校验配置，打印参数速查表辅助排查。
    支持直接传入 custom config JSON 覆盖默认配置。
"""
import json, sys
from pathlib import Path


def _build_config(task_dir: Path, target_hw: str, pulsar_image: str,
                  input_dtype: str = "FP32", custom_config: dict | None = None) -> dict:
    """从 model_meta.json 构建 Pulsar2 编译配置，custom_config 可覆盖任意字段。

    Args:
        input_dtype: Pulsar2 proto DataType 名 (FP32/U8/S8/FP16...)
        custom_config: 可选的用户覆盖配置 dict，顶级 key 直接合并
    """
    from magnetar.docker_util import get_pulsar2_proto_enums_cached

    meta = json.loads((task_dir / "export" / "model_meta.json").read_text(encoding="utf-8"))
    enums = get_pulsar2_proto_enums_cached(pulsar_image)
    dt = enums["DataType"]

    if input_dtype not in dt:
        valid = [k for k in dt if not k.startswith("Default")]
        raise ValueError(f"input_dtype '{input_dtype}' 不在 Pulsar2 DataType 中。可选: {valid}")

    input_info = meta["inputs"][0]
    input_name = input_info["name"]
    input_shape = input_info["shape"]
    input_layout = input_info.get("layout", "NCHW")

    shape_str = "x".join(str(d) for d in input_shape)
    input_shapes = f"{input_name}:{shape_str}"

    if input_dtype == "U8":
        mean, std = [0, 0, 0], [255, 255, 255]
        calib_format = "Numpy"
    elif input_dtype == "FP32":
        mean, std = [], []
        calib_format = "Numpy"
    else:
        mean, std = [], []
        calib_format = "Numpy"

    config = {
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

    if custom_config:
        for k, v in custom_config.items():
            if k in config and isinstance(config[k], dict) and isinstance(v, dict):
                config[k].update(v)
            else:
                config[k] = v

    return config


def _validate_and_warn(config: dict, image: str, task_dir: Path):
    """编译前校验 Pulsar2 配置，打印警告和参考信息。"""
    from magnetar.pulsar2_ref import validate_config, get_enums, print_calib_cheatsheet

    enums = get_enums(image)
    warnings = validate_config(config, enums)

    if warnings:
        print("\n" + "=" * 60)
        print("  ⚠ Pulsar2 配置校验发现问题:")
        print("=" * 60)
        for w in warnings:
            print(f"  ❌ {w}")
        print()
        print("  💡 可用选项速查:")
        print_calib_cheatsheet(enums)
        print()
        print("  💡 生成参考配置: python magnetar/pulsar2_ref.py --save")
        print()

        # Generate a reference config for this hardware
        from magnetar.pulsar2_ref import generate_reference_config
        ref = generate_reference_config(enums, config.get("target_hardware", "AX650"))
        ref_path = task_dir / "pulsar2_reference_config.json"
        ref_path.write_text(ref)
        print(f"  📄 参考配置已保存: {ref_path}")

    return len(warnings) == 0


def run(task_dir: Path, target_hw: str, pulsar_image: str,
        input_dtype: str = "FP32", custom_config: dict | None = None,
        skip_validation: bool = False) -> None:
    from magnetar.docker_util import docker_pulsar2

    compile_dir = task_dir / "compile"
    compile_dir.mkdir(parents=True, exist_ok=True)

    config = _build_config(task_dir, target_hw, pulsar_image, input_dtype, custom_config)

    # Pre-build validation
    if not skip_validation:
        ok = _validate_and_warn(config, pulsar_image, task_dir)
        if not ok:
            resp = input("\n  ⚠ 配置有警告，是否继续编译？[y/N] ")
            if resp.lower() != "y":
                print("  已取消编译。请修正配置后重试。")
                sys.exit(1)

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
