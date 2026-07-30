"""Pulsar2 配置参考——自动从 Docker 镜像 proto 文件解析可用选项。

用法:
  python magnetar/pulsar2_ref.py            # 打印校准速查表
  python magnetar/pulsar2_ref.py --save-ref  # 生成参考配置到参考文件
"""
import json, os, re, sys, textwrap
from collections import OrderedDict
from pathlib import Path


def _read_proto(image, path):
    import subprocess
    return subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "cat", image, path],
        capture_output=True, text=True, timeout=30
    ).stdout


def _parse_enums(text):
    enums = OrderedDict()
    current = None
    for line in text.splitlines():
        m = re.match(r'^enum\s+(\w+)\s*\{', line)
        if m:
            current = m.group(1)
            enums.setdefault(current, OrderedDict())
            continue
        m = re.match(r'^\s+(\w+)\s*=\s*(\d+)\s*;', line)
        if m and current:
            enums[current][m.group(1)] = int(m.group(2))
        if line.strip() == '}' and current:
            current = None
    return enums


def get_enums(image):
    """解析 common.proto + build_config.proto 中所有枚举。

    Returns: {"DataType": {"U8": 1, "FP32": 10}, "QuantMethod": {"MinMax": 0, ...}, ...}
    """
    enums = OrderedDict()
    for path in ["/opt/pulsar2/yamain/config/common.proto",
                 "/opt/pulsar2/yamain/config/build_config.proto"]:
        text = _read_proto(image, path)
        for k, v in _parse_enums(text).items():
            enums[k] = v
    return enums


# ─── 表格打印 ───

def _fmt_enum(enums_dict, name, sep=", "):
    return sep.join(enums_dict.get(name, {}).keys())

def print_calib_cheatsheet(image_or_enums):
    """打印校准/量化速查表。"""
    if isinstance(image_or_enums, str):
        enums = get_enums(image_or_enums)
    else:
        enums = image_or_enums

    sections = [
        ("模型类型 (model_type)",      "ModelType",            ""),
        ("目标硬件 (target_hardware)", "HardwareType",        ""),
        ("NPU 模式 (npu_mode)",       "NPUMode",              "AX650: NPU1/NPU2/NPU3。NPU3=三核"),
        ("标定方法 (calibration_method)", "QuantMethod",      "KL→平滑分布; MinMax→通用; Percentile→抗outlier; MSE→最精确最慢"),
        ("标定数据格式 (calibration_format)", "DataFormat",   "Numpy(.npy)最常用; Image→视觉; Binary→原始"),
        ("量化数据类型 (data_type)",   "DataType",             "U8/S8=INT8; U16/S16=U16; FP32=不量化"),
    ]
    width = 72
    for title, enum_name, note in sections:
        print()
        print(f"{'─'*width}")
        print(f"  {title}")
        print(f"{'─'*width}")
        items = [(k, v) for k, v in enums.get(enum_name, {}).items()]
        # Filter irrelevant entries for DataType
        if enum_name == "DataType":
            items = [(k,v) for k,v in items if 'Default' not in k and k not in ('U32','S32','U64','S64','BF16','NVFP4')]
        for k, v in items:
            print(f"  {k:<20} = {v}")
        if note:
            print(f"  ── {note}")


# ─── 参考配置生成 ───

_REF = """{{
  // ── 必填基础项 ──
  "input": "/workspace/export/model.onnx",
  "output_dir": "/workspace/compile",
  "output_name": "model.axmodel",
  "work_dir": "/workspace/compile/work",

  "model_type": "ONNX",               // {MODEL_TYPES}
  "target_hardware": "{HW}",          // {HARDWARE_TYPES}
  "npu_mode": "NPU3",                 // {NPU_MODES}
  "input_shapes": "input:1x3x224x224",       // name:dim1xdim2x...

  // ── ONNX 优化 ──
  "onnx_opt": {{
    "disable_onnx_optimization": false,
    "enable_onnxsim": false,          // 推荐 true
    "model_check": true
  }},

  // ── 量化配置 ──
  // 标定方法: {CALIB_METHODS}
  "quant": {{
    "calibration_method": "MinMax",   // 通用默认; Transformer 推荐 KL

    // --- 标定数据 ---
    "input_configs": [{{
      "tensor_name": "input",
      "calibration_dataset": "/workspace/export/calib_data/input.tar.gz",
      "calibration_format": "Numpy",  // {CALIB_FORMATS}
      "calibration_size": 8,
      "calibration_mean": [],
      "calibration_std": []
    }}],

    // --- 逐层精度 (可选, 格式: op_type + 类型) ---
    // 可用 data_type / weight_data_type / output_data_type: {DATA_TYPES}
    // weight_data_type 仅支持 S8 或 FP32
    "layer_configs": [
      {{ "op_type": "Conv",   "data_type": "U8",  "weight_data_type": "S8",  "output_data_type": "U8" }},
      {{ "op_type": "MatMul", "data_type": "U16", "weight_data_type": "U16", "output_data_type": "U16" }}
    ],

    // --- 可选量化增强 (三选一) ---
    // "enable_smooth_quant": true,      // SmoothQuant: 平滑激活/权重
    // "smooth_quant_alpha": 0.5,
    // "enable_brecq": true,             // Brecq: 逐块重建
    // "enable_lsq": true,               // LSQ: 可学习步长 (需 QAT)

    // --- 其他 ---
    "highest_mix_precision": false,   // 必须 false
    "precision_analysis": false       // true=输出每层精度报告
  }},

  // ── 编译 ──
  "compiler": {{ "check": 3 }}        // 0=无 1=逐值 2=统计 3=余弦验证
}}"""


def generate_reference_config(image_or_enums, target_hardware="AX650"):
    """生成带注释的参考配置 JSON。"""
    if isinstance(image_or_enums, str):
        enums = get_enums(image_or_enums)
    else:
        enums = image_or_enums

    return _REF.format(
        HW=target_hardware,
        MODEL_TYPES=_fmt_enum(enums, "ModelType"),
        HARDWARE_TYPES=_fmt_enum(enums, "HardwareType"),
        NPU_MODES=_fmt_enum(enums, "NPUMode"),
        CALIB_METHODS=_fmt_enum(enums, "QuantMethod"),
        CALIB_FORMATS=_fmt_enum(enums, "DataFormat"),
        DATA_TYPES=_fmt_enum(enums, "DataType"),
    )


# ─── 配置校验 ───

def validate_config(config: dict, enums: dict) -> list[str]:
    """校验配置字典，返回警告列表（空列表 = 配置通过）。"""
    warnings = []

    mt = config.get("model_type", "ONNX")
    if mt not in enums.get("ModelType", {}):
        warnings.append(f"model_type '{mt}' 不在: {_fmt_enum(enums, 'ModelType')}")

    q = config.get("quant", {})
    cm = q.get("calibration_method", "")
    if cm and cm not in enums.get("QuantMethod", {}):
        warnings.append(f"calibration_method '{cm}' 不在: {_fmt_enum(enums, 'QuantMethod')}")

    for ic in q.get("input_configs", []):
        cf = ic.get("calibration_format", "")
        if cf and cf not in enums.get("DataFormat", {}):
            warnings.append(f"calibration_format '{cf}' 不在: {_fmt_enum(enums, 'DataFormat')}")

    for lc in q.get("layer_configs", []):
        for field in ["data_type", "weight_data_type", "output_data_type"]:
            dt = lc.get(field, "")
            if dt and dt not in enums.get("DataType", {}):
                warnings.append(f"layer_config.{field} '{dt}' 不在: {_fmt_enum(enums, 'DataType')}")
            if field == "weight_data_type" and dt not in ("S8", "FP32", ""):
                warnings.append(f"weight_data_type 仅支持 S8/FP32，当前 '{dt}'")

    # check for conflicting flags
    flags = sum(1 for k in ["enable_smooth_quant", "enable_brecq", "enable_lsq"] if q.get(k))
    if flags > 1:
        warnings.append("enable_smooth_quant/brecq/lsq 只能三选一")

    return warnings


# ─── CLI ───

def _get_image():
    import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
    from magnetar.docker_util import latest_pulsar2_image
    return latest_pulsar2_image()

def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Pulsar2 配置参考工具")
        print("  python magnetar/pulsar2_ref.py            # 打印校准速查表")
        print("  python magnetar/pulsar2_ref.py --ref      # 输出参考配置 JSON")
        print("  python magnetar/pulsar2_ref.py --save     # 保存参考配置到文件")
        return

    image = _get_image()
    enums = get_enums(image)

    if "--ref" in sys.argv or "--save" in sys.argv:
        ref = generate_reference_config(enums)
        if "--save" in sys.argv:
            path = Path("pulsar2_reference_config.json")
            path.write_text(ref)
            print(f"\u2705 参考配置已保存: {path.resolve()}")
            print("  (含 // 注释，非标准 JSON，供手动参考)")
        else:
            print(ref)
    else:
        print(f"Pulsar2 {image} — 校准/量化速查表")
        print_calib_cheatsheet(enums)


if __name__ == "__main__":
    main()
