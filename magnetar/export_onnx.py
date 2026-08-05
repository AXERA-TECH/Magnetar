"""EXPORT 通用化：任意 PyTorch 模型 -> 静态 ONNX。

设计原则（对应 Magnetar 非 MobileNet 模型的导出约定）：

1. 先尝试最简单路径 ``torch.onnx.export(dynamo=False)``；
2. 失败后逐级降级：opset 降低 -> dynamo/``torch.export`` -> onnxsim 后处理；
3. 每一步失败原因都记录进 ``export_attempts``，全部失败时抛出带诊断报告的
   ``ExportError``，由 Agent 据此决定人工处理方向（固定动态维度、替换算子等）；
4. 成功后自动完成：ONNX Runtime 对分（cosine >= 0.99）、静态 shape 检查、
   ``model_meta.json``、校准数据、``export_report.md``。

Agent 使用方式见 ``scripts/export_onnx.py --help``，核心 Python API 见
``export_to_onnx()``。
"""
from __future__ import annotations

import importlib.util
import json
import tarfile
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np


@dataclass
class ExportAttempt:
    """单次导出尝试的记录，写入 export_attempts / 诊断报告。"""

    path: str
    status: str  # ok | fail | skipped
    detail: str = ""
    static_shapes: bool | None = None
    cosine: float | None = None
    error: str = field(default="", repr=False)


class ExportError(RuntimeError):
    """所有导出路径都失败。携带 attempts 供 Agent 诊断。"""

    def __init__(self, message: str, attempts: list[ExportAttempt], report: Path | None = None):
        super().__init__(message)
        self.attempts = attempts
        self.report = report

    def __str__(self) -> str:
        lines = [super().__str__()]
        for a in self.attempts:
            status = {"ok": "OK", "fail": "FAIL", "skipped": "-"}[a.status]
            detail = a.detail or a.error
            lines.append(f"  [{status}] {a.path}: {detail[:200]}")
        if self.report:
            lines.append(f"  诊断报告: {self.report}")
        return "\n".join(lines)


def _short(exc: Exception, limit: int = 1200) -> str:
    text = str(exc).strip()
    if not text:
        text = traceback.format_exc(limit=3).strip().splitlines()[-1]
    return text[:limit]


def _normalize_example_inputs(example_inputs: Any) -> tuple[tuple[Any, ...] | dict[str, Any], list[str]]:
    """归一化 example_inputs，返回 (torch.onnx.export 接受的输入, 输入名列表)。"""
    if isinstance(example_inputs, dict):
        names = [f"input_{i}" for i in range(len(example_inputs))]
        return example_inputs, names
    if isinstance(example_inputs, tuple):
        seq: tuple[Any, ...] = example_inputs
    elif isinstance(example_inputs, list):
        seq = tuple(example_inputs)
    else:
        seq = (example_inputs,)
    names = [f"input_{i}" for i in range(len(seq))]
    return seq, names


def _torch_reference_output(model, example_inputs):
    """eval + no_grad 下取原模型参考输出，保持 tuple 语义。"""
    import torch

    model = model.eval()
    with torch.no_grad():
        out = model(*example_inputs) if isinstance(example_inputs, (tuple, list)) else model(example_inputs)
    if isinstance(out, (tuple, list)):
        return [o.detach().cpu().numpy().astype(np.float32) for o in out]
    if isinstance(out, dict):
        return [o.detach().cpu().numpy().astype(np.float32) for o in out.values()]
    return [out.detach().cpu().numpy().astype(np.float32)]


def _load_model_from_script(script: Path):
    """执行用户 load 脚本，返回 (model, example_inputs)。

    脚本约定：定义 ``build()`` 返回 ``(model, example_inputs)``，或定义
    ``load_model()`` 只返回 model。example_inputs 为 Tensor / tuple / list / dict。
    """
    spec = importlib.util.spec_from_file_location("_magnetar_load_script", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载脚本: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "build"):
        return module.build()
    if hasattr(module, "load_model"):
        return module.load_model(), None
    raise AttributeError(
        f"{script} 未定义 build() 或 load_model()；请提供返回 (model, example_inputs) 的 build()"
    )


def _load_model_by_arch(arch: str, checkpoint: Path | None):
    """按架构标识加载模型：torchvision:<name> | timm:<name> | hf:<repo>。"""
    import torch

    kind, _, name = arch.partition(":")
    if kind == "torchvision":
        import torchvision.models as tvm

        factory = getattr(tvm, name, None)
        if factory is None:
            raise AttributeError(f"torchvision 中没有模型 {name!r}")
        model = factory(weights=None).eval()
    elif kind == "timm":
        import timm

        model = timm.create_model(name, pretrained=False).eval()
    elif kind == "hf":
        from transformers import AutoModel, AutoModelForAudioClassification, AutoModelForCausalLM, AutoModelForImageClassification

        model = None
        for cls in (AutoModel, AutoModelForImageClassification, AutoModelForAudioClassification, AutoModelForCausalLM):
            try:
                model = cls.from_pretrained(name).eval()
                break
            except Exception:
                continue
        if model is None:
            raise RuntimeError(f"无法从 HuggingFace 加载 {name!r}，请改用 --load-script")
    else:
        raise ValueError(f"不支持的架构标识 {arch!r}；支持 torchvision:<name> / timm:<name> / hf:<repo>")

    if checkpoint is not None:
        ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
        if isinstance(ckpt, dict) and "state_dict" in ckpt:
            ckpt = ckpt["state_dict"]
        if isinstance(ckpt, dict):
            model.load_state_dict(ckpt, strict=False)
        else:
            model.load_state_dict(ckpt.state_dict(), strict=False)
    return model


def _example_inputs_from_shapes(shapes: list[str]) -> tuple[tuple[Any, ...], list[str]]:
    """把 '1x3x224x224' 这类描述转成随机 float32 张量。"""
    import torch

    seq = tuple(torch.randn(*[int(d) for d in s.strip().lower().split("x")]) for s in shapes)
    return seq, [f"input_{i}" for i in range(len(seq))]


def _export_legacy(model, example_inputs, onnx_path, input_names, output_names, opset):
    import torch

    kwargs: dict[str, Any] = dict(
        opset_version=opset,
        dynamo=False,
        do_constant_folding=True,
    )
    if input_names:
        kwargs["input_names"] = input_names
    if output_names:
        kwargs["output_names"] = output_names
    torch.onnx.export(model, example_inputs, str(onnx_path), **kwargs)


def _export_dynamo(model, example_inputs, onnx_path, input_names, output_names, opset):
    import torch

    kwargs: dict[str, Any] = dict(opset_version=opset, dynamo=True)
    if input_names:
        kwargs["input_names"] = input_names
    if output_names:
        kwargs["output_names"] = output_names
    torch.onnx.export(model, example_inputs, str(onnx_path), **kwargs)


def _simplify_onnx(onnx_path: Path) -> str:
    import onnx

    from onnxsim import simplify

    model = onnx.load(str(onnx_path))
    simplified, ok = simplify(model)
    if not ok:
        return "onnxsim simplify 返回 not ok"
    onnx.save(simplified, str(onnx_path))
    return "onnxsim 简化完成"


def _check_static(onnx_path: Path) -> tuple[bool, list[dict[str, Any]]]:
    """检查输入/输出是否全部静态，返回 (is_static, 动态维度列表)。"""
    import onnx

    model = onnx.load(str(onnx_path))
    model = onnx.shape_inference.infer_shapes(model)
    initializers = {i.name for i in model.graph.initializer}
    dynamic: list[dict[str, Any]] = []

    def scan(nodes: Iterable[onnx.ValueInfoProto], kind: str):
        for vi in nodes:
            if vi.name in initializers:
                continue
            shape = vi.type.tensor_type.shape
            for idx, dim in enumerate(shape.dim):
                if (dim.HasField("dim_value") and dim.dim_value > 0) or (
                    dim.HasField("dim_param") and str(dim.dim_param).isdigit()
                ):
                    continue
                dynamic.append({"kind": kind, "name": vi.name, "dim": idx, "param": str(dim.dim_param)})

    scan(model.graph.input, "input")
    scan(model.graph.output, "output")
    return not dynamic, dynamic


def _run_ort(onnx_path: Path, input_names: list[str], example_inputs):
    """ORT CPU 推理；example_inputs 为 tuple 或 dict。返回 (输出名列表, numpy 输出 list)。"""
    import onnxruntime as ort

    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    if isinstance(example_inputs, dict):
        feed = {k: np.ascontiguousarray(v.detach().cpu().numpy(), dtype=np.float32) for k, v in example_inputs.items()}
    else:
        feed = {name: np.ascontiguousarray(t.detach().cpu().numpy(), dtype=np.float32) for name, t in zip(input_names, example_inputs)}
    outputs = sess.run(None, feed)
    out_names = [o.name for o in sess.get_outputs()]
    return out_names, [np.asarray(o).astype(np.float32) for o in outputs]


def _write_meta_and_calib(
    task_dir: Path,
    *,
    model_name: str,
    opset: int,
    onnx_path: Path,
    input_names: list[str],
    sample_tensors: list[Any],
    ref_outputs: list[np.ndarray],
    ort_outputs: list[np.ndarray],
    out_names: list[str],
    cosine: float,
    attempts: list[ExportAttempt],
    sample_variants: int,
) -> dict[str, Any]:
    import onnx

    ed = Path(task_dir) / "export"
    onnx.checker.check_model(onnx.load(str(onnx_path)))
    proto = onnx.load(str(onnx_path))
    initializers = {i.name for i in proto.graph.initializer}

    def shape_of(vi) -> list[int]:
        dims = []
        for d in vi.type.tensor_type.shape.dim:
            dims.append(d.dim_value if d.HasField("dim_value") else -1)
        return dims

    inputs_meta = [
        {"name": vi.name, "shape": shape_of(vi), "dtype": "float32", "layout": "NCHW"}
        for vi in proto.graph.input
        if vi.name not in initializers
    ]
    outputs_meta = [
        {"name": vi.name, "shape": shape_of(vi), "dtype": "float32"} for vi in proto.graph.output
    ]
    meta = {
        "model_name": model_name,
        "framework": "pytorch",
        "inputs": inputs_meta,
        "outputs": outputs_meta,
        "opset": opset,
        "torch_onnx_cosine": cosine,
        "export_attempts": [asdict(a) for a in attempts],
    }
    (ed / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # 校准数据：每个输入一份扰动序列 + tar.gz（多输入模型可逐个配置 calibration_dataset）
    for name, tensor in zip(input_names, sample_tensors):
        sample_np = np.ascontiguousarray(tensor.detach().cpu().numpy(), dtype=np.float32)
        calib_dir = ed / "calib_data" / name
        calib_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(sample_variants):
            np.save(calib_dir / f"{idx:04d}.npy", np.clip(sample_np + (idx * 0.01), -1, 1).astype(np.float32))
        tar_path = ed / "calib_data" / f"{name}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            for npy in sorted(calib_dir.glob("*.npy")):
                tar.add(npy, arcname=npy.name)

    report_lines = [
        "# Export Report",
        "",
        f"- Model: {model_name}",
        f"- ONNX: {onnx_path.name}",
        f"- Opset: {opset}",
        f"- Torch-ONNX cosine: {cosine:.6f}",
        f"- Inputs: {', '.join(i['name'] + str(i['shape']) for i in inputs_meta)}",
        f"- Outputs: {', '.join(o['name'] + str(o['shape']) for o in outputs_meta)}",
        "",
        "## Export attempts",
        "",
    ]
    for a in attempts:
        report_lines.append(f"- [{a.status}] {a.path}: {(a.detail or a.error or '')[:240]}")
    (ed / "export_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return meta


def _export_to_onnx_impl(
    task_dir: Path | str,
    *,
    model=None,
    example_inputs=None,
    load_script: str | Path | None = None,
    arch: str | None = None,
    checkpoint: str | Path | None = None,
    input_names: list[str] | None = None,
    output_names: list[str] | None = None,
    opset: int = 17,
    model_name: str = "model",
    sample_variants: int = 4,
    cosine_threshold: float = 0.99,
    require_static: bool = True,
) -> dict[str, Any]:
    """通用导出主入口。

    参数：
      model: 已加载的 nn.Module（优先）。
      example_inputs: Tensor / tuple / list / dict[str, Tensor]。
      load_script: 用户脚本路径，定义 build() 返回 (model, example_inputs)。
      arch: torchvision:<name> | timm:<name> | hf:<repo>。
      checkpoint: 权重路径（配合 arch 使用）。
      input_names / output_names: 显式命名；缺省自动 input_0.. / output_0..。
      opset: 首选 opset（失败自动降到 13/11）。

    返回 dict: onnx_path / model_meta / attempts / cosine / input_names / output_names。
    全部路径失败时抛 ExportError（含诊断报告路径）。
    """
    import torch

    task_dir = Path(task_dir)
    ed = task_dir / "export"
    ed.mkdir(parents=True, exist_ok=True)
    attempts: list[ExportAttempt] = []
    onnx_path = ed / "model.onnx"

    def record(path: str, status: str, detail: str = "", error: str = "", static: bool | None = None, cos: float | None = None):
        attempts.append(ExportAttempt(path=path, status=status, detail=detail, error=error, static_shapes=static, cosine=cos))

    # ---- 解析模型与示例输入 ----
    if model is None:
        if load_script:
            model, script_inputs = _load_model_from_script(Path(load_script))
            if example_inputs is None:
                example_inputs = script_inputs
        elif arch:
            model = _load_model_by_arch(arch, Path(checkpoint) if checkpoint else None)
        else:
            raise ValueError("必须提供 model 或 load_script 或 arch 三者之一")
    model = model.eval()

    if example_inputs is None:
        raise ValueError("缺少 example_inputs；可用 --input-shapes 或 load 脚本提供")
    export_inputs, auto_input_names = _normalize_example_inputs(example_inputs)
    input_names = input_names or auto_input_names

    # 参考输出（torch）：失败也走统一诊断，不暴露裸异常
    try:
        ref_outputs = _torch_reference_output(model, export_inputs)
    except Exception as exc:
        err = _short(exc)
        record("torch 参考输出", "fail", error=err)
        report = ed / "export_report.md"
        report.write_text(
            "# Export Report\n\n原模型 forward 失败（在导出前），无法计算参考输出：\n\n"
            f"- {err}\n\n建议：先用最小示例确认模型可正常推理（eval + no_grad），"
            "再检查 load 脚本/架构与 example_inputs 是否匹配。\n",
            encoding="utf-8",
        )
        raise ExportError(f"原模型 forward 失败: {err}", attempts, report) from exc
    np.save(ed / "source_output.npy", np.asarray(ref_outputs[0]).astype(np.float32))
    first_tensor = export_inputs[0] if isinstance(export_inputs, (tuple, list)) else next(iter(export_inputs.values()))
    np.save(ed / "sample_input.npy", np.ascontiguousarray(first_tensor.detach().cpu().numpy(), dtype=np.float32))

    # ---- 路径 1：最简导出（opset 失败自动降级 13/11）----
    last_error = ""
    for attempt_opset in ([opset] + [o for o in (13, 11) if o != opset]):
        try:
            _export_legacy(model, export_inputs, onnx_path, input_names, output_names, attempt_opset)
            record(f"torch.onnx.export(dynamo=False, opset={attempt_opset})", "ok")
            opset = attempt_opset
            last_error = ""
            break
        except Exception as exc:
            last_error = _short(exc)
            record(f"torch.onnx.export(dynamo=False, opset={attempt_opset})", "fail", error=last_error)

    # ---- 路径 2：dynamo / torch.export ----
    if last_error:
        try:
            _export_dynamo(model, export_inputs, onnx_path, input_names, output_names, opset)
            record(f"torch.onnx.export(dynamo=True, opset={opset})", "ok")
            last_error = ""
        except Exception as exc:
            last_error = _short(exc)
            record(f"torch.onnx.export(dynamo=True, opset={opset})", "fail", error=last_error)

    if last_error:
        report = ed / "export_report.md"
        report.write_text(
            "# Export Report\n\n全部导出路径失败：\n\n"
            + "\n".join(f"- [{a.status}] {a.path}: {a.error[:200]}" for a in attempts)
            + "\n\n建议：1) 检查 load 脚本/架构是否可正常 forward；2) 固定动态维度（如序列长度）后重试；"
              "3) 对特殊算子（TTS/控制流）改用人工导出并参考 issues/ 中的案例。\n",
            encoding="utf-8",
        )
        raise ExportError(f"ONNX 导出失败（{len([a for a in attempts if a.status=='fail'])} 个路径尝试失败）", attempts, report)

    # ---- 验证：checker + 静态 shape + ORT 对分 ----
    import onnx

    try:
        onnx.checker.check_model(onnx.load(str(onnx_path)))
    except Exception as exc:
        record("onnx.checker", "fail", error=_short(exc))
        try:
            detail = _simplify_onnx(onnx_path)
            record("onnxsim simplify 后重查", "ok", detail=detail)
            onnx.checker.check_model(onnx.load(str(onnx_path)))
        except Exception as exc2:
            raise ExportError(f"ONNX 模型校验失败且简化后仍失败: {_short(exc2)}", attempts, ed / "export_report.md") from exc2

    is_static, dynamic_dims = _check_static(onnx_path)
    if require_static and not is_static:
        dyn_summary = "; ".join(f"{d['kind']} {d['name']}[{d['dim']}]={d['param']}" for d in dynamic_dims[:8])
        record("static shape 检查", "fail", detail=f"动态维度: {dyn_summary}")
        raise ExportError(
            f"模型含动态 shape（{dyn_summary}）。请固定动态维度（如 batch/序列长度）后重新导出，"
            f"或在 load 脚本中把示例输入设为实际部署形状；诊断报告: {ed / 'export_report.md'}",
            attempts,
            ed / "export_report.md",
        )
    record("static shape 检查", "ok", detail=f"{len(dynamic_dims)} 个动态维度" if dynamic_dims else "全部静态")

    try:
        out_names, ort_outputs = _run_ort(onnx_path, input_names, export_inputs)
    except Exception as exc:
        record("onnxruntime 推理", "fail", error=_short(exc))
        try:
            detail = _simplify_onnx(onnx_path)
            record("onnxsim simplify 后重跑", "ok", detail=detail)
            out_names, ort_outputs = _run_ort(onnx_path, input_names, export_inputs)
        except Exception as exc2:
            raise ExportError(f"ONNX Runtime 推理失败且简化后仍失败: {_short(exc2)}", attempts, ed / "export_report.md") from exc2
    else:
        record("onnxruntime 推理", "ok")

    from magnetar.stages.simulate import cosine

    paired = list(zip(ref_outputs, ort_outputs))
    cosines = [cosine(r, o) for r, o in paired]
    cos_min = min(cosines) if cosines else 0.0
    for name, cos in zip(out_names, cosines):
        record(f"torch-vs-ORT 对分 {name}", "ok" if cos >= cosine_threshold else "fail", detail=f"cosine={cos:.6f}", cos=cos)
    if cos_min < cosine_threshold:
        raise ExportError(
            f"Torch-ONNX 对分 cosine={cos_min:.6f} < {cosine_threshold}（各输出: {[round(c, 6) for c in cosines]}）。"
            "请检查导出配置或模型实现；诊断报告见 export_report.md",
            attempts,
            ed / "export_report.md",
        )

    sample_tensors = list(export_inputs) if isinstance(export_inputs, (tuple, list)) else list(export_inputs.values())
    meta = _write_meta_and_calib(
        task_dir,
        model_name=model_name,
        opset=opset,
        onnx_path=onnx_path,
        input_names=input_names,
        sample_tensors=sample_tensors,
        ref_outputs=ref_outputs,
        ort_outputs=ort_outputs,
        out_names=out_names,
        cosine=cos_min,
        attempts=attempts,
        sample_variants=sample_variants,
    )
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"\n- EXPORT: {onnx_path} (cosine={cos_min:.6f})\n")
    from magnetar.stages.state import mark_stage
    mark_stage(
        task_dir, "EXPORT",
        artifacts={"onnx": str(onnx_path), "model_meta": str(ed / "model_meta.json")},
        metrics={"torch_onnx_cosine": cos_min},
        summary=f"EXPORT cosine={cos_min:.6f}",
    )
    return {
        "onnx_path": onnx_path,
        "model_meta": meta,
        "attempts": attempts,
        "cosine": cos_min,
        "input_names": input_names,
        "output_names": out_names,
    }


def export_to_onnx(
    task_dir: Path | str,
    **kwargs,
) -> dict[str, Any]:
    """通用导出主入口（失败时在 .magnetar-state.json 标记 blocked 并确保诊断报告落盘）。"""
    from magnetar.stages.state import mark_stage

    try:
        return _export_to_onnx_impl(task_dir, **kwargs)
    except ExportError as exc:
        if exc.report is not None and not Path(exc.report).is_file():
            attempts = exc.attempts or []
            Path(exc.report).write_text(
                "# Export Report\n\n全部导出路径失败：\n\n"
                + "\n".join(f"- [{a.status}] {a.path}: {(a.detail or a.error or '')[:200]}"
                            for a in attempts)
                + "\n",
                encoding="utf-8",
            )
        mark_stage(
            Path(task_dir), "EXPORT", status="blocked",
            summary=f"EXPORT 失败: {str(exc).splitlines()[0][:160]}",
        )
        raise


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("请通过 scripts/export_onnx.py 或 python -m magnetar.export_onnx 使用")
