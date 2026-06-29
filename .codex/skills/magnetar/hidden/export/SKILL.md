---
name: export
description: Hidden stage for magnetar. Export the acquired model to static-shape ONNX, validate it against the source model, and generate model_meta.json plus calibration data.
---

# EXPORT

目标：在 `TASK_DIR/export/` 生成可被 Pulsar2 编译的静态 ONNX、`model_meta.json`、校准集和导出报告。

## 策略

按优先级选择：

1. 已有静态 ONNX：验证后复制为 `export/model.onnx`。
2. 上游导出脚本：改造成可复现的 `export-static-onnx.py`。
3. HuggingFace Transformers：优先 `optimum-cli export onnx`，失败后使用 `torch.onnx.export`。
4. PyTorch 权重：读取 README/源码，编写最小原模型推理脚本和静态导出脚本。
5. 其他框架：先寻找官方 ONNX 导出路径；无法判断时 STOP。

## 必须产物

- `test-source.py` 或等价原模型推理脚本。
- `export-static-onnx.py`。
- `model.onnx`，静态 shape，batch 固定。
- `model_meta.json`，字段：
  - `model_name`
  - `framework`
  - `inputs`: name、shape、dtype、layout、preprocess
  - `outputs`: name、shape、dtype、semantic
  - `opset`
  - `tokenizer_path` 或其他附属资源路径。
- `calib_data/`，优先真实数据。
- `export_report.md`。

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
