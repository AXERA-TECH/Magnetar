"""COMPILE: Pulsar2 编译 ONNX → AXMODEL。

v3:
- 配置生成改为多输入感知（model_meta.json 里每个输入独立 input_configs /
  input_processors），不再只取第一个输入；
- 编译前三重预检，全部通过才启动编译（独立包/镜像通用）：
  1) proto schema 字段级校验（未知字段/类型/枚举/必填，本地秒级）；
  2) 业务规则 + model_meta 交叉校验（输入名、校准集内容、工作流约束）；
  3) config-check 权威兜底（用 Pulsar2 自身的 build_config_pb2 解析，
     独立包本地执行 / docker 镜像内执行）。
  MAGNETAR_SKIP_PREFLIGHT=1 可跳过预检（仅排障用）。
"""
import json, os, re, sys
from pathlib import Path


def _build_config(task_dir: Path, target_hw: str, pulsar_image: str,
                  input_dtype: str = "FP32", custom_config: dict | None = None) -> dict:
    """从 model_meta.json 构建 Pulsar2 编译配置，custom_config 可覆盖任意字段。

    Args:
        input_dtype: Pulsar2 proto DataType 名 (FP32/U8/S8/FP16...)
        custom_config: 可选的用户覆盖配置 dict，顶级 key 直接合并

    多输入模型：每个输入独立 input_configs + input_processors，
    校准包路径统一为 /workspace/export/calib_data/<输入名>.tar.gz。
    """
    from magnetar.docker_util import get_pulsar2_proto_enums_cached
    from magnetar.docker_util import parse_backend

    meta = json.loads((task_dir / "export" / "model_meta.json").read_text(encoding="utf-8"))
    enums = get_pulsar2_proto_enums_cached(pulsar_image)
    dt = enums["DataType"]

    if input_dtype not in dt:
        valid = [k for k in dt if not k.startswith("Default")]
        raise ValueError(f"input_dtype '{input_dtype}' 不在 Pulsar2 DataType 中。可选: {valid}")

    input_infos = meta["inputs"]
    if not input_infos:
        raise ValueError("model_meta.json 缺少 inputs")

    # 后端决定配置里的路径前缀：docker 用 /workspace，独立包用宿主绝对路径
    kind, _ = parse_backend(pulsar_image)
    mount_root = "/workspace" if kind == "docker" else str(task_dir.resolve())

    def ws(rel: str) -> str:
        return f"{mount_root}/{rel}"

    input_shapes = ";".join(
        f'{i["name"]}:{"x".join(str(d) for d in i["shape"])}' for i in input_infos
    )

    input_configs, input_processors = [], []
    for info in input_infos:
        name = info["name"]
        shape = info["shape"]
        layout = info.get("layout", "NCHW")
        channels = shape[1] if len(shape) == 4 else None
        if input_dtype == "U8":
            if channels != 3:
                raise ValueError(
                    f"input_dtype=U8 只支持 3 通道视觉输入（RGB），"
                    f"当前 '{name}' shape={shape}；请改用 FP32 或在 custom_config 覆盖"
                )
            calib_mean, calib_std = [0, 0, 0], [255, 255, 255]
            src_layout = "NHWC"
            tensor_format = src_format = "RGB"
        else:
            calib_mean, calib_std = [], []
            src_layout = layout
            tensor_format = src_format = "RGB" if channels == 3 else ""
        input_configs.append({
            "tensor_name": name,
            "calibration_dataset": ws(f"export/calib_data/{name}.tar.gz"),
            "calibration_format": "Numpy",
            "calibration_size": 30,
            "calibration_mean": calib_mean,
            "calibration_std": calib_std,
        })
        ip = {
            "tensor_name": name,
            "tensor_layout": layout,
            "src_dtype": input_dtype,
            "src_layout": src_layout,
        }
        if tensor_format:
            ip.update({"tensor_format": tensor_format, "src_format": src_format})
        input_processors.append(ip)

    config = {
        "input": ws("export/model.onnx"),
        "output_dir": ws("compile"),
        "output_name": "model.axmodel",
        "work_dir": ws("compile/work"),
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
            "input_configs": input_configs,
            "calibration_method": "MinMax",
            "precision_analysis": True,
            "precision_analysis_method": "EndToEnd",
            "highest_mix_precision": False,
        },
        "input_processors": input_processors,
    }

    if custom_config:
        for k, v in custom_config.items():
            if k in config and isinstance(config[k], dict) and isinstance(v, dict):
                config[k].update(v)
            else:
                config[k] = v

    return config


def _preflight(task_dir: Path, config: dict, image: str):
    """编译前预检（本地秒级）：
    1) proto schema 字段级校验；
    2) 业务规则 + model_meta 交叉校验（输入名/校准集/工作流约束）。
    Returns: (errors, warnings, calib_counts)
    """
    from magnetar.io_format import validate_calibration_archive
    from magnetar.proto_schema import load_schema, parse_input_shapes_str
    from magnetar.pulsar2_ref import get_enums, validate_config

    errors: list[str] = []
    warnings: list[str] = []

    # 1. 字段级（未知字段/类型/枚举/必填），本地 proto 缓存解析
    schema = load_schema(image)
    errors += schema.validate(config)

    # 2. 业务规则（U8 std=255、weight_data_type、三选一等）
    #    会导致错误行为的项进 errors（硬阻断），纯建议项进 warnings
    hard_markers = ("U8 输入", "三选一", "仅支持", "不一致")
    for w in validate_config(config, get_enums(image)):
        (errors if any(m in w for m in hard_markers) else warnings).append(w)

    # 3. input_shapes / tensor_name 与 model_meta 交叉校验
    meta_path = task_dir / "export" / "model_meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_inputs = {i["name"]: i.get("shape") for i in meta.get("inputs", [])}
        shapes = parse_input_shapes_str(config.get("input_shapes", ""))
        for name in shapes:
            if name not in meta_inputs:
                errors.append(
                    f"input_shapes 输入名 '{name}' 不在 model_meta.inputs "
                    f"({list(meta_inputs)})；tensor_name 必须与 ONNX graph.input 一致"
                )
    else:
        meta_inputs = {}

    # 4. 校准集内容预检（npy shape/dtype/数量），并统计样本数
    calib_counts: dict[str, int] = {}
    for ic in config.get("quant", {}).get("input_configs", []):
        name = ic.get("tensor_name", "")
        if ic.get("calibration_format") != "Numpy" or name in ("", "DEFAULT"):
            continue
        ds = ic.get("calibration_dataset", "")
        if ds.startswith("/workspace/"):
            local = task_dir / ds[len("/workspace/"):]
        else:
            local = Path(ds)
        shape = meta_inputs.get(name)
        if shape is None:
            errors.append(
                f"input_configs.tensor_name '{name}' 不在 model_meta.inputs 中，"
                "校准数据会匹配不上"
            )
            continue
        res = validate_calibration_archive(local, name, shape)
        calib_counts[name] = res["samples"]
        errors += [f"calib[{name}] {e}" for e in res["errors"]]
        warnings += [f"calib[{name}] {w}" for w in res["warnings"]]

    # 5. 工作流硬约束
    if config.get("quant", {}).get("highest_mix_precision") is not False:
        errors.append("quant.highest_mix_precision 必须为 false（工作流约束）")
    if not (task_dir / "export" / "model.onnx").is_file():
        errors.append(f"缺少 ONNX 模型: {task_dir / 'export' / 'model.onnx'}")

    return errors, warnings, calib_counts


def run(task_dir: Path, target_hw: str, pulsar_image: str,
        input_dtype: str = "FP32", custom_config: dict | None = None,
        skip_validation: bool = False) -> None:
    from magnetar.docker_util import parse_backend, resolve_backend, run_pulsar2
    from magnetar.errors import MagnetarError
    from magnetar.stages.events import log_error

    compile_dir = task_dir / "compile"
    compile_dir.mkdir(parents=True, exist_ok=True)

    backend = pulsar_image or resolve_backend()
    config = _build_config(task_dir, target_hw, backend, input_dtype, custom_config)

    # 预检（本地 schema + 校准集 + 业务规则）
    if not skip_validation and not os.environ.get("MAGNETAR_SKIP_PREFLIGHT"):
        errors, warnings, calib_counts = _preflight(task_dir, config, backend)
        # 用实际样本数收敛 calibration_size（Pulsar2 会对 size 与数据集取 min）
        for ic in config.get("quant", {}).get("input_configs", []):
            n = calib_counts.get(ic.get("tensor_name", ""))
            if n:
                ic["calibration_size"] = min(int(ic.get("calibration_size", 30)), n)
        if errors:
            print("\n" + "=" * 60)
            print("  ❌ COMPILE preflight 未通过，已停止编译：")
            print("=" * 60)
            for e in errors:
                print(f"  ❌ {e}")
            print("  💡 修正上述问题后重试；仅排障可用 MAGNETAR_SKIP_PREFLIGHT=1 跳过")
            exc = MagnetarError("compile_failed", f"COMPILE preflight 未通过（{len(errors)} 项错误，见上方列表）")
            log_error(task_dir, exc, stage="COMPILE")
            raise exc
        if warnings:
            print("[COMPILE] preflight 警告:")
            for w in warnings:
                print(f"  ⚠ {w}")
        else:
            print("[COMPILE] preflight OK（schema + 校准集 + 业务规则）")

    config_path = compile_dir / "pulsar2_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    kind, name = parse_backend(backend)
    print(f"[COMPILE] backend={kind} ({name})  input_dtype={input_dtype}  "
          f"input_shapes={config['input_shapes']}")

    # 权威兜底：用 Pulsar2 自身 build_config_pb2 解析一次（独立包/镜像通用）
    if (not skip_validation
            and not os.environ.get("MAGNETAR_SKIP_PREFLIGHT")
            and not os.environ.get("MAGNETAR_SKIP_CONFIG_CHECK")):
        from magnetar.docker_util import docker_pulsar2_config_check
        try:
            out = docker_pulsar2_config_check(backend, str(task_dir.resolve()))
            print(f"[COMPILE] {out.strip()}")
        except RuntimeError as e:
            if "CONFIG_ERROR" in str(e):
                exc = MagnetarError(
                    "compile_failed",
                    "config-check 未通过（Pulsar2 自身解析报错，见上方输出）。"
                    "请按报错修正 compile/pulsar2_config.json 后重试",
                )
                log_error(task_dir, exc, stage="COMPILE")
                raise exc from e
            print(f"[COMPILE] 警告: config-check 不可用（{e}），继续编译")

    cfg_arg = "/workspace/compile/pulsar2_config.json" if kind == "docker" else str(config_path)
    run_pulsar2(
        backend, str(task_dir.resolve()),
        f"pulsar2 build --config {cfg_arg}",
        timeout=3600,
        log_file=compile_dir / "compile.log",
    )

    axmodel = compile_dir / "model.axmodel"
    if not axmodel.is_file():
        summary = summarize_compile_log(task_dir)
        from magnetar.stages.state import mark_stage
        exc = MagnetarError("compile_failed", f"Pulsar2 未生成 {axmodel}")
        log_error(task_dir, exc, stage="COMPILE")
        mark_stage(
            task_dir, "COMPILE", status="blocked",
            metrics={"compile_errors": summary.get("errors", [])},
            summary=f"COMPILE 失败，见 compile/compile.log 摘要: {summary.get('errors', [])[:2]}",
        )
        raise exc

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
    from magnetar.stages.state import mark_stage
    mark_stage(
        task_dir, "COMPILE",
        artifacts={"axmodel": str(axmodel)},
        metrics={"axmodel_size_kb": size_kb},
        summary=f"COMPILE OK axmodel={size_kb:.1f} KB",
    )
    print(f"[COMPILE] Done. model.axmodel = {size_kb:.1f} KB")


def summarize_compile_log(task_dir: Path) -> dict:
    """从 compile/compile.log 提取关键指标（MACs/大小/错误行），禁止 Agent 全量读日志。"""
    log_path = Path(task_dir) / "compile" / "compile.log"
    result: dict = {"macs": None, "size_bytes": None, "errors": [], "tail": ""}
    if not log_path.is_file():
        result["errors"] = ["compile.log 不存在"]
        return result
    text = log_path.read_text(encoding="utf-8", errors="replace")
    axmodel = Path(task_dir) / "compile" / "model.axmodel"
    result["size_bytes"] = axmodel.stat().st_size if axmodel.is_file() else None

    for pattern, key in [
        (r"[Mm][Aa][Cc][Ss]?[\s:=]*([\d.]+[eE]?[\d.]*)", "macs"),
    ]:
        matches = re.findall(pattern, text)
        if matches:
            result[key] = matches[-1]

    seen = set()
    for line in text.splitlines():
        low = line.lower()
        if any(k in low for k in ("error", "failed", "exception", "fatal")) and "errorcode" not in low:
            trimmed = line.strip()[:240]
            if trimmed and trimmed not in seen:
                seen.add(trimmed)
                result["errors"].append(trimmed)
        if len(result["errors"]) >= 8:
            break
    result["tail"] = text[-1500:]
    return result
