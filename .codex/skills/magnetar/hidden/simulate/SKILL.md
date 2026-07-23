---
name: simulate
description: Hidden stage for magnetar. Compare ONNX outputs with AXMODEL simulation outputs using task-relevant metrics.
---

# SIMULATE

## 执行

`metrics = magnetar.stages.simulate.run(task_dir, sample, pulsar_image, board=board)`

内部逻辑：
1. 计算 ONNX 参考输出
2. **若 BOARD 可用**：上传模型到板端，`/opt/bin/ax_run_model` 直接跑（秒级），下载结果与 ONNX 对比
3. **若 BOARD 不可用或板端失败**：回退 `pulsar2 run` Docker 仿真（分钟级）

## 验证
- cosine_similarity ≥ 0.99
- MAE、max_abs_diff 记录在 `simulate_report.md`
- ≥3 组输入样本，报告均值 ± 标准差

## STOP
- cosine < 0.99：先查 `issues/` 目录已知修复，无匹配则 STOP
- AXMODEL 输出全零/异常 → 检查校准归一化配置
