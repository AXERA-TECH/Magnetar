---
name: export
description: Hidden stage for magnetar. Export the acquired model to static-shape ONNX, validate it against the source model, and generate model_meta.json plus calibration data.
---

# EXPORT

## 执行
MobileNet 可直接调用 `sample = magnetar.stages.export.run_mobilenet(task_dir)`。
其他模型需 Agent 自行实现：导出静态 ONNX → onnx.checker 验证 → ONNX Runtime 与原模型对分（cosine ≥ 0.99）→ 生成 `model_meta.json` 和校准数据。
校准数据**尽量用真实业务数据**（`run_generic(calibration_data=…)` 或 `scripts/export_onnx.py --calib-dir`）；
随机/扰动数据仅兜底，需在 export_report.md 标注来源。

## 验证
- `export/model.onnx` 为静态 shape，onnxruntime 可加载
- `export/model_meta.json` 含完整 input/output name/shape/dtype/layout
- Torch/ONNX cosine ≥ 0.99
- `export/calib_data/input.tar.gz` 存在（≥3 组样本）
- `export/export_report.md` 标注校准来源（real 业务数据 / perturbed 兜底）

## STOP
- ONNX 对分失败（cosine < 0.99）
- 模型含动态 shape 且静态化失败
- 仅有随机/扰动校准数据且用户未确认（校准集应尽量用真实业务数据，随机数据可能在真实业务上崩）
