---
name: export
description: Hidden stage for magnetar. Export the acquired model to static-shape ONNX, validate it against the source model, and generate model_meta.json plus calibration data.
---

# EXPORT

目标：在 `TASK_DIR/export/` 生成可被 Pulsar2 编译的静态 ONNX、`model_meta.json`、校准集和导出报告。

## 策略

按优先级选择：

1. 已有静态 ONNX（来自 ACQUIRE 阶段的 `origin/`）：不得直接复制为 `export/model.onnx` 即视为完成。必须执行以下全部验证步骤后，方可进入下一阶段：
   - `onnx.checker.check_model()` 通过。
   - `onnxruntime.InferenceSession()` 可加载并完成一次推理。
   - 确认所有输入为静态 shape；存在动态维度时必须静态化。
   - 生成 `model_meta.json`（含完整 input/output shape/dtype/layout）。
   - 生成校准数据（≥3 组，优先真实数据）。
   - 生成 `export_report.md`。
   所有产物写入 `TASK_DIR/export/`，包括从 `origin/` 复制过来的 ONNX。
2. 上游导出脚本：改造成可复现的 `export-static-onnx.py`。
3. HuggingFace Transformers：优先 `optimum-cli export onnx`，失败后使用 `torch.onnx.export`。
4. PyTorch 权重：读取 README/源码，编写最小原模型推理脚本和静态导出脚本。
5. 其他框架：先寻找官方 ONNX 导出路径；无法判断时 STOP。

## Pulsar2 静态 ONNX 约束

Pulsar2 仅支持静态 shape 的 ONNX。所有输入维度必须为具体整数值，不得保留动态维度名（如 `batch_size`、`feats_length`）。`input_shapes` 配置无法覆盖 ONNX 图中已定义的动态维度——模型本身必须静态化。

若 ACQUIRE 阶段的 ONNX 存在动态 shape，必须在 EXPORT 阶段完成静态化：
- 用 `onnxruntime` 加载后进行 shape inference（`onnx.shape_inference`）。
- 若 shape inference 无法解析动态维度，用 `onnx.tools.update_model_dims` 或等价方法将 `dim_param` 重写为 `dim_value`。
- 验证 `onnx.checker.check_model()` 通过，且再次确认所有输入 shape 为具体整数。

禁止将动态 ONNX 带入 COMPILE 阶段。

## 必须产物

- `test-source.py` 或等价原模型推理脚本。
- `export-static-onnx.py`。
- `model.onnx`，静态 shape，batch 固定。
- `model_meta.json`，字段：
  - `model_name`
  - `framework`
  - `inputs`: name、shape、dtype、layout、preprocess（必须明确 ONNX 期望输入数值范围，如 [0,1] 或 [0,255]，这是 COMPILE 阶段确定 calibration_std 的依据）
  - `outputs`: name、shape、dtype、semantic
  - `opset`
  - `onnx_size_bytes`: ONNX 文件字节数（用于后续压缩比计算）。
  - `tokenizer_path` 或其他附属资源路径。
- `calib_data/`，优先真实数据。
- `export_report.md`。

- 记录 ONNX 文件大小（字节）到 `model_meta.json` 的 `onnx_size_bytes` 和 `export_report.md`。


## 输入范围确认

必须确认 ONNX 模型期望的输入数值范围（大多数 PyTorch 模型为 [0,1]），记录到 `model_meta.json` 的 preprocess 字段。这是 COMPILE 阶段确定 `calibration_std` 的关键依据。

验证方法：分别用 [0,1] 和 [0,255] 范围的随机输入跑 ONNX，对比两者输出 cosine。若 < 0.99，模型对输入范围敏感，必须明确文档化。

## 验证

1. `onnx.checker.check_model()` 通过。
2. `onnxruntime.InferenceSession()` 可加载。
3. ONNX 与原模型使用同一输入对分，记录 cosine、MAE、max abs diff 或任务指标。
4. 校准数据 dtype 与编译配置一致；默认数值输入用 `float32`。

## STOP

- 原模型推理无法跑通。
- 导出入口不明确。
- ONNX 与原模型对分失败。
- 只能生成随机校准数据且未获用户确认。
- 动态 shape 无法静态化。
