---
name: export
description: Hidden stage for magnetar. Export the acquired model to static-shape ONNX, validate it against the source model, and generate model_meta.json plus calibration data.
---

# EXPORT

## 执行
MobileNet 可直接调用 `sample = magnetar.stages.export.run_mobilenet(task_dir)`。
其他模型需 Agent 自行实现：导出静态 ONNX → onnx.checker 验证 → ONNX Runtime 与原模型对分（cosine ≥ 0.99）→ 生成 `model_meta.json` 和校准数据。

## 验证
- `export/model.onnx` 为静态 shape，onnxruntime 可加载
- `export/model_meta.json` 含完整 input/output name/shape/dtype/layout
- Torch/ONNX cosine ≥ 0.99
- `export/calib_data/input.tar.gz` 存在（≥3 组样本）

## STOP
- ONNX 对分失败（cosine < 0.99）
- 模型含动态 shape 且静态化失败
- 仅有随机校准数据且用户未确认
