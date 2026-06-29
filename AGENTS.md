# AGENTS.md

本仓库包含 Magnetar 模型部署工作流。所有 Codex 回复默认使用中文。

## 项目目标

将任意来源模型（git仓库、HuggingFace、本地路径）转换为 AX 芯片 axmodel，并生成 Python/C++ 推理 SDK。

## Codex 工作流

当用户要求部署、导出、编译、仿真、上板、SDK生成，或运行 Magnetar 工作流时，使用：

`.codex/skills/axmodel-pipeline/SKILL.md`

## 强制约束

- 必须按 `ACQUIRE → INIT → EXPORT → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE` 顺序推进。
- 遇到 `STOP` 必须暂停等待用户确认。
- 所有执行过程记录到 `task.md` 和 `analysis.md`。
- 不得污染原始模型工程，所有中间文件写入 `TASK_DIR`。
- 调试解决的问题记录到 `issues/`。

## 目录约定

```text
TASK_DIR/
  origin/       # 原始模型
  export/       # ONNX + model_meta.json [+ tokenizer/]
  compile/      # axmodel
  simulate/     # 精度报告
  sdk/python/   # Python SDK
  sdk/cpp/      # C++ SDK + toolchain-aarch64.cmake
  package/      # 最终产物
  cache/
  task.md
  analysis.md
```
