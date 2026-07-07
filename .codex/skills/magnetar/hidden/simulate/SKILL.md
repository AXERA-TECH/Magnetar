---
name: simulate
description: Hidden stage for magnetar. Compare ONNX outputs with AXMODEL simulation outputs using task-relevant metrics.
---

# SIMULATE

目标：用多组输入对比 ONNX 与 AXMODEL 仿真输出，判断编译精度是否达标，并记录仿真推理延迟。

## 步骤

1. 从 EXPORT 阶段保留的真实样本中选择 ≥3 组测试输入（优先从校准集或真实数据中均匀选取）。
2. 编写并保留：
   - `simulate/run_onnx.py`
   - `simulate/run_axmodel.sh` 或等价 Pulsar2 仿真脚本
   - `simulate/compare_outputs.py`
3. 对每组输入分别运行 ONNX 和 AXMODEL。
4. 记录输出 tensor 名称、shape、dtype。
5. 按任务选择指标：
   - 分类：cosine、Top-k、MAE、max abs diff
   - 检测：框坐标误差、类别一致性、NMS 前后差异
   - 分割：像素准确率、mIoU、logits cosine
   - 通用：cosine、MSE、MAE、分位数误差
6. 对每组输入独立计算指标，报告均值 ± 标准差（例如 "cosine: 0.997 ± 0.002"）。
7. 测量仿真推理延迟：在 `pulsar2 run` 命令外包裹 `time`，或记录 Docker 命令总耗时，作为单次仿真推理延迟（ms）。
   - 若使用 Docker，用容器内 `time` 或外部 `time` 均可，报告其中一次运行的耗时。
8. 生成 `simulate/simulate_report.md`，含：
   - 每组输入的指标表格
   - 各指标的均值 ± 标准差
   - 仿真单次推理延迟（ms）

## 默认通过条件

通用张量默认 `cosine >= 0.99`（基于均值）。任务指标比单一相对误差优先。

## STOP

精度不达标、仿真工具不可用且无法替代、或需要修改编译配置时停止等待用户确认。
