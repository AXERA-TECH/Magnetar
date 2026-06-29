---
name: simulate
description: Hidden stage for magnetar. Compare ONNX outputs with AXMODEL simulation outputs using task-relevant metrics.
---

# SIMULATE

目标：用相同输入对比 ONNX 与 AXMODEL 仿真输出，判断编译精度是否达标。

## 步骤

1. 从 EXPORT 阶段保留的真实样本中选择测试输入。
2. 编写并保留：
   - `simulate/run_onnx.py`
   - `simulate/run_axmodel.sh` 或等价 Pulsar2 仿真脚本
   - `simulate/compare_outputs.py`
3. 使用同一输入分别运行 ONNX 和 AXMODEL。
4. 记录输出 tensor 名称、shape、dtype。
5. 按任务选择指标：
   - 分类：cosine、Top-k、MAE、max abs diff
   - 检测：框坐标误差、类别一致性、NMS 前后差异
   - 分割：像素准确率、mIoU、logits cosine
   - 通用：cosine、MSE、MAE、分位数误差
6. 生成 `simulate/simulate_report.md`。

## 默认通过条件

通用张量默认 `cosine >= 0.99`。任务指标比单一相对误差优先。

## STOP

精度不达标、仿真工具不可用且无法替代、或需要修改编译配置时停止等待用户确认。
