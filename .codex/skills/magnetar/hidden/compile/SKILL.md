---
name: compile
description: Hidden stage for magnetar. Compile static ONNX to AXMODEL with Pulsar2 and record compile artifacts.
---

# COMPILE

## 执行
`magnetar.stages.compile.run(task_dir, target_hw, pulsar_image)`

## 关键约束
- `highest_mix_precision` 必须为 `false`
- `calibration_std` 用 255（非 0.004）——Pulsar2 用 `/std` 公式
- 编译前确认 ONNX 为静态 shape

## 验证
- `compile/model.axmodel` 存在且非空
- `compile/compile_report.md` 含 MACs、大小、压缩比、编译耗时

## STOP
- Pulsar2 编译失败且需改 ONNX → 退回 EXPORT
- 输入预处理配置与导出验证不一致
