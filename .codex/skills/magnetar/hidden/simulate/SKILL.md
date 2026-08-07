---
name: simulate
description: Hidden stage for magnetar. Compare ONNX outputs with AXMODEL simulation outputs using task-relevant metrics.
---

# SIMULATE

## 执行

`metrics = magnetar.stages.simulate.run(task_dir, sample, pulsar_image, board=board, target_hw=TARGET_HARDWARE)`

内部逻辑：
1. 计算 ONNX 参考输出
2. **有板必上板**：BOARD 已配置直接用；未配置时先 `magnetar.board_util.select_board(TARGET_HARDWARE, BOARD_PASSWORD)` 找空闲板
3. **上板**：先 `ensure_remote_infer(board)` 确保 ax-remote-infer 已装（18500 通就跳过，未装自动静默安装），再上传模型，`/opt/bin/ax_run_model` 直接跑（秒级），下载结果与 ONNX 对比
4. **仅当找不到板或板端失败**：回退 `pulsar2 run` Docker 仿真（分钟级）

输入/输出格式（bin 命名、input_list、reshape）一律用 `magnetar/io_format.py`，规范见 `docs/input-format-cheatsheet.md`。

## 验证
- cosine_similarity ≥ 0.99
- MAE、max_abs_diff 记录在 `simulate_report.md`
- ≥3 组输入样本，报告均值 ± 标准差

## STOP
- cosine < 0.99：先查 `issues/` 目录已知修复；INT8/U16/混合精度全部尝试仍不达标时，STOP 前先向用户提议上 QAT（必须用官方 `AXERA-TECH/QAT.axera`，走 QAT→QDQ ONNX，需训练数据/时间，用户确认后进入）
- AXMODEL 输出全零/异常 → 检查校准归一化配置
