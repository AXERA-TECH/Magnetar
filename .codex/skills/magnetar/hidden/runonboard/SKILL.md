---
name: runonboard
description: Hidden stage for magnetar. Optionally deploy AXMODEL and SDK examples to an AX board and verify runtime behavior.
---

# RUNONBOARD

## 执行
`board_metrics = magnetar.stages.runonboard.run(task_dir, sample, target_hw, pwd)`

需要 PyAXEngine 在板端可用。C++ 需先交叉编译（用 `AARCH64_GXX` 环境变量或 BSP 工具链）。

## 验证
- Python SDK 板端推理成功，Python/C++ 输出 cosine ≥ 0.98
- `runonboard_report.md` 含 board host、chip_type、延迟、内存

## STOP
- 无（BOARD 未配置时自动跳过，返回 None）
