# AGENTS.md

本仓库包含 Magnetar 模型部署工具。所有 Agent 回复默认使用中文。

## 项目目标

将远程或本地浮点模型转换为 AX 芯片客户交付包：

`模型 → ONNX → Pulsar2 编译 → AXMODEL → 仿真验证 → Python/C++ SDK → 交付包`

## 工具库

Agent 负责编排和决策。`magnetar/stages/*.py` 提供确定性执行函数：

| 模块 | 函数 | 用途 |
|------|------|------|
| `magnetar.config` | `load_config()` | 读取 `.magnetarrc` + 环境变量 |
| `magnetar.docker_util` | `latest_pulsar2_image()`, `docker_pulsar2()` | Docker/Pulsar2 封装 |
| `magnetar.board_util` | `select_board()`, `ssh()`, `scp_to()`, `scp_from()` | AX 板端操作 |
| `magnetar.stages.init` | `run(config)` → `task_dir` | 创建 TASK_DIR 结构 |
| `magnetar.stages.acquire` | `run(task_dir, source)` | 获取模型到 origin/ |
| `magnetar.stages.export` | `run_mobilenet(task_dir)` → `sample` | MobileNet ONNX 导出+验证+校准 |
| `magnetar.stages.toolchain` | `run()` → `pulsar_image` | 验证 Pulsar2 Docker 可用 |
| `magnetar.stages.compile` | `run(task_dir, target_hw, image)` | Pulsar2 编译 AXMODEL |
| `magnetar.stages.simulate` | `run(task_dir, sample, image, board=board)` → `metrics` | 精度对分（优先板端 ax_run_model，回退 pulsar2 run） |
| `magnetar.stages.sdk_gen` | `run_mobilenet_python()`, `run_mobilenet_cpp()` | 生成 Python/C++ SDK |
| `magnetar.stages.runonboard` | `run(task_dir, sample, hw, pwd)` → `metrics` | 板端部署验证 |
| `magnetar.stages.package` | `assemble(task_dir, metrics, image)` → `pkg` | 组装交付包 |

非 MobileNet 模型：Agent 需自行实现 ONNX 导出逻辑并正确填写 `model_meta.json`。

## 执行流程

严格按以下顺序推进 9 阶段，不可跳过。每阶段完成后更新 `task.md` 和 `analysis.md`。

状态机（回退/重试/循环）由 `workflows/magnetar.yaml` 控制。

## STOP 点

必须暂停等待用户确认：
- `SOURCE`、`TARGET_HARDWARE` 未提供
- ONNX 与原模型对分失败（cosine < 0.99）
- 模型含动态 shape 且静态化失败
- Pulsar2 不可用
- 编译失败需改 ONNX → 退回 EXPORT
- SIMULATE 精度不达标（先查 `issues/`，无匹配再 STOP）
- 需要私有凭据

BOARD 缺失不是 STOP——自动跳过 RUNONBOARD。

## 配置

优先读取 `.magnetarrc`（shell 风格 key=value），环境变量可覆盖。详见 `.magnetarrc.example`。

## 目录约定

```
TASK_DIR/
  origin/       export/       compile/       simulate/
  sdk/python/   sdk/cpp/      runonboard/    package/    cache/
  task.md       analysis.md
```

产物不得污染原始模型工程。

## 关键技术点

### 校准归一化对齐

Pulsar2 用 `(img - mean) / std`，libdet 用 `(input - mean) * std`。必须反向对齐：

| 组件 | 配置 | 输入范围 |
|------|------|----------|
| Pulsar2 校准 | `calibration_std = 255` | uint8/255 = [0,1] |
| libdet 推理 | `std = 1/255` | uint8 × (1/255) = [0,1] |

**常见错误**：`calibration_std = 0.004`（即 1/255）→ 校准输入 [0,65025] → 板端全零。

### 量化
默认 INT8。U16 仅 INT8 cosine < 0.99 时尝试。`highest_mix_precision` 必须为 false。

### 编译
ONNX 必须静态 shape。编译前用 ONNX Runtime 验证。

### 分发
- GitHub：源码 + model_convert（客户可复现）
- HuggingFace：预编译模型 + binary（客户直接用），不含 model_convert
- HF README 需 YAML frontmatter

## 验证期望

- ONNX 导出可复现，Torch/ONNX 对分 cosine ≥ 0.99
- Pulsar2 配置 `highest_mix_precision` 为 false
- Python SDK `import <sdk>` 通过，默认 `AxEngineExecutionProvider`
- C++ SDK cmake configure 通过
- `ax_run_model` 仅用于 smoke check，不能替代 SDK 验证
- PACKAGE 产出独立 git 项目，板端自验证通过

## 爱芯开发知识

- Pulsar2 镜像: https://hf-mirror.com/AXERA-TECH/Pulsar2
- Pulsar2 文档: https://pulsar2-docs.readthedocs.io/zh-cn/latest/
- 爱芯 HF: https://hf-mirror.com/AXERA-TECH
- 爱芯 GitHub: https://github.com/AXERA-TECH
- AX650 BSP SDK: https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub
- AX620E 交叉编译器: Arm GNU 9.2 aarch64
- LLM 编译: https://github.com/AXERA-TECH/ax-llm
- 本机 Docker 可能已安装 Pulsar2，优先使用最新版本
- 调试问题记录到 `issues/`，命名 `序号_模型名_阶段_问题简述.md`
