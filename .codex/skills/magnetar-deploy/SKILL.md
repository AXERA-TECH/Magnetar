---
name: magnetar-deploy
description: Deploy floating-point AI models to AXera AX chips with Pulsar2. Use when Codex is asked to run the Magnetar workflow, export ONNX, prepare calibration data, compile AXMODEL, simulate or compare ONNX vs AXMODEL outputs, debug Pulsar2 quantization/precision issues, or run a model on an AX development board.
---

# Magnetar Deploy

始终用中文与用户沟通。按 `INIT -> EXPORT -> COMPILE -> SIMULATE -> RUNONBOARD` 顺序执行，不得跳阶段。遇到 `STOP` 必须暂停等待用户确认。

详细阶段说明见 [references/workflow.md](references/workflow.md)。在执行任一阶段前先读取该文件。

## 输入参数

尽量从用户请求或仓库上下文中解析：

- `REPO`: 原始模型工程、本地模型路径或 Git URL。
- `TASK_DIR`: 任务工作目录；未指定时使用 `todos/work/<timestamp>-<model-name>/`。
- `MODEL_NAME`: 模型名；未指定时从 `REPO` basename 推断。
- `TARGET_HARDWARE`: 目标芯片，例如 `AX650`、`AX620E`。
- `BOARD`: 板端 SSH/scp 信息；仅 RUNONBOARD 阶段需要。

缺少会影响当前阶段的参数时，在最近的 `STOP` 点询问；若无法开始 INIT，则先向用户询问最小必要信息。

## 执行规则

- 所有命令必须在对应阶段目录内执行。
- 所有脚本、日志、中间产物、调试样本必须写入 `TASK_DIR` 下的阶段目录或 `cache/`。
- 原始工程放入 `TASK_DIR/origin/`，不要直接修改上游工程；需要 patch 时优先使用 monkeypatch 或复制后的工作副本。
- 每完成一个关键动作，更新 `TASK_DIR/task.md`；每次分析错误、做出取舍、修改配置，都更新 `TASK_DIR/analysis.md`。
- 修复过的可复用问题必须沉淀到仓库根目录 `issues/`。

## 质量门槛

- ONNX 必须静态 shape，batch 也应静态。
- 校准集优先真实数据，通常使用 4/16/32 个样本。
- 校准数据、ONNX 推理输入、AXMODEL 仿真输入必须保持同一预处理链。
- Pulsar2 配置禁止使用 `"highest_mix_precision": true`。
- 精度判断必须结合任务语义，不要只看相对误差。

## STOP 行为

到达 `STOP` 时：

1. 说明当前阶段产物、验证结果和风险。
2. 给出下一步可选动作。
3. 停止执行，等待用户明确回复。

除非用户已经在同一消息中明确授权继续，否则不得越过 STOP。
