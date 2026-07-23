---
name: simulate
description: Hidden stage for magnetar. Compare ONNX outputs with AXMODEL simulation outputs using task-relevant metrics.
---

# SIMULATE

## 执行
`metrics = magnetar.stages.simulate.run(task_dir, sample, pulsar_image)`

## 验证
- cosine_similarity ≥ 0.99
- MAE、max_abs_diff 记录在 `simulate_report.md`
- ≥3 组输入样本，报告均值 ± 标准差

## STOP
- cosine < 0.99：先查 `issues/` 目录已知修复，无匹配则 STOP
- AXMODEL 仿真输出全零/异常 → 检查校准归一化配置
