# AGENTS.md

本仓库包含 Magnetar 模型部署工作流。所有 Codex 回复默认使用中文。

## 项目目标

Magnetar 用于辅助完成从远程或本地浮点模型到 AX 芯片客户交付包的部署流程：

`远程/本地模型 -> ONNX -> Pulsar2 编译 -> AXMODEL -> 仿真验证 -> Python/C++ SDK -> 客户交付包`

## Codex 工作流

当用户要求部署、导出、编译、仿真、上板、调试 Pulsar2/AXModel，或要求运行 Magnetar 工作流时，优先使用本仓库的 Codex skill：

`.codex/skills/magnetar/SKILL.md`

如果 skill 未被自动发现，先读取该文件，再按其中流程执行。

## 强制约束

- 必须按 `ACQUIRE -> INIT -> EXPORT -> TOOLCHAIN -> COMPILE -> SIMULATE -> SDK-GEN -> RUNONBOARD -> PACKAGE` 顺序推进。
- `RUNONBOARD` 只有用户提供板端信息时执行；未提供时记录为跳过并继续打包。
- 遇到流程中标记为 `STOP` 的位置，必须暂停并等待用户确认或补充输入。
- 所有执行过程、关键命令、产物路径、错误分析必须记录到任务工作目录内的 `task.md` 和 `analysis.md`。
- 不得污染原始模型工程。调试脚本、中间文件、导出模型、编译缓存等必须写入任务工作目录。
- 调试中遇到并解决的问题，应在仓库 `issues/` 下新增记录，命名格式为 `序号_模型名_阶段_问题简述.md`。
- 不要在提交信息或用户可见产物中提及 AI 身份。

## 目录约定

默认任务目录为 `todos/work/<timestamp>-<model-name>/`，结构如下：

```text
TASK_DIR/
  origin/       # 原始模型工程或模型文件
  export/       # 导出脚本、ONNX 验证脚本、校准集生成脚本
  compile/      # Pulsar2 配置和编译产物
  simulate/     # ONNX 与 AXMODEL 仿真对分
  sdk/python/   # Python SDK
  sdk/cpp/      # C++ SDK + toolchain-aarch64.cmake
  runonboard/   # 板端验证文件
  package/      # 客户交付 git 项目根目录
  cache/        # 跨阶段中间文件和临时调试文件
  task.md
  analysis.md
```

## 验证期望

- EXPORT 阶段必须优先使用真实输入数据；没有真实数据时，应在 STOP 点向用户确认随机数据、用户提供路径、或可下载数据源。
- ONNX 导出必须生成可复现脚本，并进行 Torch/ONNX 或原始模型/ONNX 对分。
- Pulsar2 配置必须明确输入 shape、输入 dtype、layout、mean/std 与推理预处理的一致性。
- 禁止开启 `"highest_mix_precision": true`。
- 精度验证优先使用任务相关指标，例如分类模型的 cosine similarity、Top-k、平均绝对误差；不要只依赖相对误差。
- Python SDK 必须通过 import 检查，并使用 `pyaxengine` 的 `AxEngineExecutionProvider` 作为默认 provider。
- C++ SDK 必须至少通过 CMake configure；存在 aarch64 工具链时执行交叉编译验证，并直接链接 AX Engine runtime。
- `ax_run_model` 只用于 AXMODEL smoke check，不得作为 Python/C++ SDK 的实现或验证替代。
- PACKAGE 阶段必须生成可独立作为 git 项目发布的目录，顶层包含 `python/`、`cpp/`、`models/`、`model_convert/` 和 `README.md`。
