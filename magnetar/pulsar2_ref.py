"""Pulsar2 配置参考——自动从 Docker 镜像 proto 文件解析可用选项。

用法:
  python magnetar/pulsar2_ref.py            # 打印校准速查表
  python magnetar/pulsar2_ref.py --cases    # 打印成功案例（输入格式固化）
  python magnetar/pulsar2_ref.py --save-ref  # 生成参考配置到参考文件
  python magnetar/pulsar2_ref.py --write-cheatsheet  # 重新生成 docs/input-format-cheatsheet.md
  python magnetar/pulsar2_ref.py --check-cheatsheet  # 校验文档与代码一致（CI）
"""
import json, os, re, sys, textwrap
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_proto(image, path):
    import subprocess
    proc = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "cat", image, path],
        capture_output=True, text=True, timeout=30
    )
    return proc.stdout if proc.returncode == 0 else ""


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

    proto 文件优先从本地缓存（cache/pulsar2/<image>/）读取，缺失时自动从
    Docker 镜像提取（见 magnetar.docker_util.extract_pulsar2_proto）。
    """
    from magnetar.docker_util import extract_pulsar2_proto, parse_proto_enums

    files = extract_pulsar2_proto(image)
    enums = OrderedDict()
    for path in (files["common.proto"], files["build_config.proto"]):
        for k, v in parse_proto_enums(path.read_text(encoding="utf-8")).items():
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


# ─── 成功案例（输入格式固化） ───

SUCCESS_CASES = [
    {
        "name": "通用单输入 FP32（MobileNetV2 / 通用导出器）",
        "scenario": "非视觉或已在 CPU 侧归一化好的输入，Numpy 校准",
        "config": {
            "quant": {
                "input_configs": [{
                    "tensor_name": "<ONNX 输入名>",
                    "calibration_dataset": "/workspace/export/calib_data/<输入名>.tar.gz",
                    "calibration_format": "Numpy",
                    "calibration_size": 30,
                    "calibration_mean": [],
                    "calibration_std": [],
                }],
                "calibration_method": "MinMax",
                "highest_mix_precision": False,
            },
            "input_processors": [{
                "tensor_name": "<ONNX 输入名>",
                "tensor_layout": "NCHW",
                "src_dtype": "FP32",
                "src_layout": "NCHW",
            }],
        },
        "data": "tar.gz 内含 {0000..NNNN}.npy，float32、带 batch 维、shape 与 input_shapes 完全一致",
        "source": "magnetar/export_onnx.py + tests/test_magnetar_mobilenet_workflow.py（已跑通）",
    },
    {
        "name": "视觉 U8 输入（YOLO，参照 yolov8l_ylb.json）",
        "scenario": "图像输入，预处理（归一化/布局转换）由工具链嵌入 axmodel",
        "config": {
            "quant": {
                "input_configs": [{
                    "tensor_name": "input",
                    "calibration_dataset": "/workspace/export/calib_data/input.tar",
                    "calibration_format": "Image",
                    "calibration_size": 32,
                    "calibration_mean": [0, 0, 0],
                    "calibration_std": [255, 255, 255],  # uint8/255 → [0,1]
                }],
                "calibration_method": "MinMax",
                "highest_mix_precision": False,
            },
            "input_processors": [{
                "tensor_name": "input",
                "tensor_format": "RGB",
                "tensor_layout": "NHWC",
                "src_format": "RGB",
                "src_dtype": "U8",
                "src_layout": "NHWC",
            }],
        },
        "data": "JPEG/PNG 打包成 tar；工具链自动插 AxDequantizeLinear(U8→FP32) + AxNormalize + AxTranspose(NHWC→NCHW)",
        "note": "calibration_std 必须是 255（非 0.004）；FP32 直通则 src_dtype=FP32、src_layout=NCHW、mean/std 显式 [0,0,0]/[1,1,1] 禁用归一化",
        "source": "magnetar/stages/compile.py（input_dtype==U8 分支）+ issues/yolo_quantization_and_compile.md",
    },
    {
        "name": "多输入校准（PiperTTS：z_p / mask）",
        "scenario": "每个输入独立配置 input_configs + tar.gz",
        "config": {
            "quant": {
                "input_configs": [
                    {"tensor_name": "z_p",  "calibration_dataset": "/workspace/.../z_p.tar.gz",  "calibration_format": "Numpy", "calibration_size": 8},
                    {"tensor_name": "mask", "calibration_dataset": "/workspace/.../mask.tar.gz", "calibration_format": "Numpy", "calibration_size": 8},
                ],
                "calibration_method": "MinMax",
                "highest_mix_precision": False,
            },
        },
        "data": "跑原 ONNX 采集中间特征（sess.run 拿各输入），存 npy 后分别打包；校准集建议 4-32 个样本",
        "source": "issues/piper_tts_experience.md §3（多输入余弦 0.987）",
    },
    {
        "name": "手写校准（MOSS-TTS-Realtime）",
        "scenario": "手工构造校准集（非通用导出器）",
        "config": {
            "quant": {
                "input_configs": [{
                    "tensor_name": "<ONNX 输入名>",   # 必须与 ONNX graph.input 一致
                    "calibration_dataset": "/workspace/.../xxx.tar.gz",
                    "calibration_format": "Numpy",
                    "calibration_size": 16,
                }],
            },
        },
        "data": "tar.gz 内 {input_name}/{index:05d}.npy 也可被接受（通用导出器用根目录 npy）；样本必须带 batch 维（如 [1,512,17]）；tensor_name 必须与 ONNX 输入名一致，校准文件名可不同",
        "source": "issues/013_moss-tts-realtime_ax650_pipeline_pitfalls.md",
    },
]


def print_success_cases() -> None:
    """打印已验证的输入格式成功案例（固化参考）。"""
    for i, c in enumerate(SUCCESS_CASES, 1):
        print()
        print(f"{'─' * 72}")
        print(f"  案例 {i}: {c['name']}")
        print(f"{'─' * 72}")
        print(f"  场景: {c['scenario']}")
        print(f"  数据: {c['data']}")
        if c.get("note"):
            print(f"  注意: {c['note']}")
        print(f"  来源: {c['source']}")
        print("  配置:")
        import json as _json
        print(_json.dumps(c["config"], ensure_ascii=False, indent=4).replace("\n", "\n    "))


# ─── cheatsheet 文档单一来源 ───

_TLDR_ROWS = [
    ("Pulsar2 校准（通用 Numpy）",
     "tar/tar.gz 内含 .npy（float32、带 batch 维、shape 与模型输入一致）",
     "MobileNetV2 测试 / 通用导出器"),
    ("Pulsar2 校准（视觉 U8）",
     "JPEG/PNG tar + mean/std=[0,0,0]/[255,255,255] + src_dtype=U8、src_layout=NHWC",
     "YOLO（yolov8l_ylb.json 参考）"),
    ("多输入校准",
     "每个输入独立 input_configs + tar.gz，tensor_name = ONNX 输入名",
     "PiperTTS"),
    ("pulsar2 run 仿真",
     "输入 {tensor名}.bin（float32 raw），输出 {输出名}.bin",
     "官方文档 + 测试"),
    ("ax_run_model 板端",
     "input_list.txt 每行一个 bin 文件名 + -m -i -o -l，输出 *.bin",
     "官方文档 + simulate.py"),
    ("axengine SDK",
     "np.ascontiguousarray(float32)，dtype 从 get_inputs()[0].dtype 读",
     "PiperTTS / MOSS-TTS"),
]

_STATIC_SECTIONS = {
    "1_intro": """\
## 1. Pulsar2 校准数据（量化输入）

- **校准样本优先真实业务数据**（真实输入或 ONNX 中间特征，如 PiperTTS 案例）；随机/扰动数据仅兜底——可能在标定集上好看，真实业务上崩
- 真实数据入口：`run_generic(calibration_data=<目录|样本列表>)` / `scripts/export_onnx.py --calib-dir`；未提供时导出器生成扰动序列，并在 `export_report.md` 标注 `perturbed 兜底`
- **COMPILE 前会自动预检校准集**（`magnetar/io_format.py::validate_calibration_archive`）：npy 的 shape/dtype/批维/数量不符会在编译前直接报错，不再等 Pulsar2 跑几分钟后才失败
""",
    "2_pulsar2_run": """\
## 2. pulsar2 run 仿真（SIMULATE 回退路径）

```bash
pulsar2 run --model /workspace/compile/model.axmodel \\
  --input_dir /workspace/simulate/input --output_dir /workspace/simulate/output
```

- 输入：`simulate/input/{输入tensor名}.bin`（float32 raw）——**文件名必须与 tensor 名一致**
- 输出：`simulate/output/{输出tensor名}.bin`（float32 raw），按 ONNX 输出 shape reshape
- 代码：`magnetar/io_format.py::write_pulsar2_run_input / read_pulsar2_run_output`，调用点 `simulate.py::_run_pulsar2`
- 案例：`tests/test_magnetar_mobilenet_workflow.py::_simulate_and_compare`（验证通过）
""",
    "3_ax_run_model": """\
## 3. ax_run_model 板端（SIMULATE 快速通道）

```bash
ax_run_model -m model.axmodel -i input_dir -o output -l input_dir/input_list.txt -w 0 -r 1
```

- `-w 0`：预热 0 次；`-r 1`：跑 1 次（仓库快速通道配置）
- 输入目录：`{输入tensor名}.bin`（float32 raw）+ `input_list.txt`（每行一个 bin 文件名）
- 输出：目录下 `*.bin`（float32 raw），单输出模型取第一个文件，reshape 成 ONNX 输出 shape
- 官方另一种目录结构（多输入/大批量时参考）：`input/0/data.bin` + `list.txt` 每行一个文件夹名，配合 `--use-tensor-name`
- 代码：`magnetar/io_format.py::write_ax_run_model_input / read_ax_run_model_output`，调用点 `simulate.py::_run_on_board`
- **上板前自动探测环境**（`magnetar/board_util.py::probe_board_env`）：ax_run_model 路径、pyaxengine、libax_engine 位置自动识别，缺依赖时报可执行提示，不再硬编码 `/opt/bin` 与 `/soc/lib`
- 注意：`Get model type failed`（issues/010）= 板端 ax 运行时与 Pulsar2 7.0 产物不兼容，换运行时/降版本，与输入格式无关
""",
    "4_sdk": """\
## 4. axengine SDK 板端输入

PiperTTS 成功用法：

```python
import axengine as axe
s = axe.InferenceSession("model.axmodel", providers=["AxEngineExecutionProvider"])
inputs = {s.get_inputs()[0].name: np.ascontiguousarray(data)}
out = s.run(None, inputs)[0]
```

- 输入必须 C-contiguous（`np.ascontiguousarray`）
- 用 `get_inputs()[0].name`，不要硬编码输入名
- MOSS-TTS（axengine 0.1.3）：无 `get_io_info`，dtype 从 `NodeArg.dtype` 读并强制转换
""",
}

_ERROR_TABLE = [
    ("校准/板端输出全零", "calibration_std=0.004（即 1/255）", "U8 用 [255,255,255]"),
    ("校准匹配不上 / 编译报 tensor 缺失", "tensor_name ≠ ONNX 输入名", "用 `onnx inspect --io model.onnx` 核对"),
    ("Numpy 校准 shape 报错", "npy 少 batch 维或与 input_shapes 不一致", "每个 npy 与输入 shape 完全一致"),
    ("pulsar2 run 无输出", "bin 文件名 ≠ tensor 名", "文件名为 ONNX 输入/输出名"),
    ("多输入只配了一个校准", "input_configs 缺项", "每个输入独立配置"),
    ("板端输出错位", "reshape 用错 shape", "用 ONNX 输出 shape（model_meta.json）"),
    ("板端 Get model type failed", "ax 运行时与编译产物不兼容", "换匹配的 ax 运行时"),
    ("视觉模型精度差", "src_layout/src_dtype 与校准不一致", "U8+NHWC 或 FP32+NCHW 显式一致"),
    ("FP32 直通被偷偷归一化", "input_processors 没显式 mean/std", "显式 [0,0,0]/[1,1,1]"),
]

_AUTHORITY = """\
## 权威依据

- Pulsar2 官方文档：
  - [Common configuration examples（校准格式/多输入/预处理嵌入）](https://pulsar2-docs.readthedocs.io/en/latest/appendix/advanced_config_examples.html)
  - [ax_run_model 模型评测工具](https://pulsar2-docs.readthedocs.io/zh-cn/latest/other_tools/ax_run_model.html)
- 仓库实现：`magnetar/export_onnx.py`、`magnetar/stages/compile.py`、`magnetar/stages/simulate.py`、`tests/`
- 经验记录：`issues/piper_tts_experience.md`、`issues/013_moss-tts-realtime_ax650_pipeline_pitfalls.md`、`issues/yolo_quantization_and_compile.md`
"""


def render_cheatsheet_markdown() -> str:
    """从 io_format.py docstring + SUCCESS_CASES + 规则表生成 cheatsheet 文档。

    单一来源：格式知识只维护在代码里（io_format.py / pulsar2_ref.py），
    docs/input-format-cheatsheet.md 是生成产物。
    """
    import textwrap

    lines: list[str] = [
        "# 输入/输出格式速查（成功案例固化）",
        "",
        "> 目的：消除 Pulsar2 校准数据与 ax_run_model 输入格式的反复试错。",
        "> 下列格式均来自仓库内已验证实现/成功案例 + 官方文档，按此执行，不要再试新格式。",
        ">",
        "> 本文件由 `python magnetar/pulsar2_ref.py --write-cheatsheet` 自动生成，请勿手改；",
        "> 知识源在 `magnetar/io_format.py`（单一来源助手）与 `magnetar/pulsar2_ref.py`（成功案例）。",
        "",
        "## TL;DR",
        "",
        "| 场景 | 格式 | 依据 |",
        "|------|------|------|",
    ]
    for scene, fmt, basis in _TLDR_ROWS:
        lines.append(f"| {scene} | {fmt} | {basis} |")
    lines.append("")
    lines.append(textwrap.dedent(_STATIC_SECTIONS["1_intro"]).strip())
    lines.append("")

    # 成功案例（从 SUCCESS_CASES 动态渲染）
    for i, c in enumerate(SUCCESS_CASES, 1):
        lines.append(f"### 1.{i} {c['name']}")
        lines.append("")
        lines.append(f"- 场景：{c['scenario']}")
        lines.append(f"- 数据：{c['data']}")
        if c.get("note"):
            lines.append(f"- 注意：{c['note']}")
        lines.append(f"- 来源：{c['source']}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(c["config"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines.append(textwrap.dedent(_STATIC_SECTIONS["2_pulsar2_run"]).strip())
    lines.append("")
    lines.append(textwrap.dedent(_STATIC_SECTIONS["3_ax_run_model"]).strip())
    lines.append("")
    lines.append(textwrap.dedent(_STATIC_SECTIONS["4_sdk"]).strip())
    lines.append("")
    lines.append("## 5. 常见错误对照表")
    lines.append("")
    lines.append("| 现象 | 根因 | 正确姿势 |")
    lines.append("|------|------|----------|")
    for symptom, cause, fix in _ERROR_TABLE:
        lines.append(f"| {symptom} | {cause} | {fix} |")
    lines.append("")
    lines.append(_AUTHORITY.strip())
    lines.append("")
    return "\n".join(lines)


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
    from magnetar.proto_schema import parse_input_shapes_str

    warnings = []
    input_names = list(parse_input_shapes_str(config.get("input_shapes", "")))

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
        tn = ic.get("tensor_name", "")
        if input_names and tn and tn != "DEFAULT" and tn not in input_names:
            warnings.append(
                f"input_configs.tensor_name '{tn}' 与 input_shapes 中的输入名不一致（{input_names}），"
                "校准数据会匹配不上"
            )
        cs = ic.get("calibration_size")
        if cs is not None and not (4 <= int(cs) <= 32):
            warnings.append(f"calibration_size={cs} 超出建议范围 [4, 32]")
        if cf == "Numpy" and not ic.get("calibration_mean") and not ic.get("calibration_std"):
            pass  # FP32 直通合法
        if cf == "Numpy" and ic.get("calibration_mean") and not ic.get("calibration_std"):
            warnings.append("Numpy 校准建议 mean/std 成对出现，避免归一化配置不完整")

    for ip in config.get("input_processors", []):
        if ip.get("src_dtype") == "U8":
            matched = any(
                ic.get("tensor_name") == ip.get("tensor_name") and ic.get("calibration_std")
                for ic in q.get("input_configs", [])
            )
            if not matched:
                warnings.append(
                    f"input_processors[{ip.get('tensor_name')}] 为 U8 输入，对应 input_configs 的 "
                    "calibration_std 应为 [255,255,255]（uint8/255 → [0,1]），当前缺失或为空"
                )

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
    from magnetar.docker_util import resolve_backend
    return resolve_backend()

def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Pulsar2 配置参考工具")
        print("  python magnetar/pulsar2_ref.py            # 打印校准速查表")
        print("  python magnetar/pulsar2_ref.py --cases    # 打印成功案例（输入格式固化）")
        print("  python magnetar/pulsar2_ref.py --ref      # 输出参考配置 JSON")
        print("  python magnetar/pulsar2_ref.py --save     # 保存参考配置到文件")
        print("  python magnetar/pulsar2_ref.py --write-cheatsheet  # 重新生成 docs/input-format-cheatsheet.md")
        print("  python magnetar/pulsar2_ref.py --check-cheatsheet  # 校验文档与代码一致")
        return

    if "--cases" in sys.argv:
        print_success_cases()
        return

    if "--write-cheatsheet" in sys.argv or "--check-cheatsheet" in sys.argv:
        doc = REPO_ROOT / "docs" / "input-format-cheatsheet.md"
        content = render_cheatsheet_markdown()
        if "--write-cheatsheet" in sys.argv:
            doc.write_text(content, encoding="utf-8")
            print(f"✅ cheatsheet 已生成: {doc}")
            return
        if doc.read_text(encoding="utf-8") != content:
            print(f"❌ {doc} 与代码不一致，请执行: python magnetar/pulsar2_ref.py --write-cheatsheet")
            sys.exit(1)
        print(f"✅ cheatsheet 与代码一致: {doc}")
        return

    backend = _get_image()
    enums = get_enums(backend)

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
        from magnetar.docker_util import parse_backend
        kind, name = parse_backend(backend)
        print(f"Pulsar2 backend: {kind} ({name}) — 校准/量化速查表")
        print_calib_cheatsheet(enums)


if __name__ == "__main__":
    main()
