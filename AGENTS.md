# AGENTS.md

本仓库包含 Magnetar 模型部署工具。所有 Agent 回复默认使用中文。

## 项目目标

将远程或本地浮点模型转换为 AX 芯片客户交付包：

`模型 → ONNX → Pulsar2 编译 → AXMODEL → 仿真验证 → Python/C++ SDK → 交付包 → 发布`

## 工具库

Agent 负责编排和决策。`magnetar/stages/*.py` 提供确定性执行函数：

| 模块 | 函数 | 用途 |
|------|------|------|
| `magnetar.config` | `load_config()` | 读取 `.magnetarrc` + 环境变量 |
| `magnetar.docker_util` | `latest_pulsar2_image()`, `docker_pulsar2()` | Docker/Pulsar2 封装 |
| `magnetar.board_util` | `select_board()`, `ssh()`, `scp_to()`, `scp_from()` | AX 板端操作 |
| `magnetar.stages.init` | `run(config)` → `task_dir` | 创建 TASK_DIR 结构 |
| `magnetar.stages.acquire` | `run(task_dir, source)`；`write_model_flow(task_dir, flow)` | 获取模型到 origin/ 并记录运行流程 |
| `magnetar.stages.export` | `run_mobilenet(task_dir)` → `sample`；`run_generic(task_dir, ...)` → `result` | MobileNet 专用 / 任意模型通用导出（先简后繁自动降级） |
| `magnetar.stages.toolchain` | `run()` → `pulsar_image` | 验证 Pulsar2 Docker 可用 |
| `magnetar.stages.compile` | `run(task_dir, target_hw, image)` | Pulsar2 编译 AXMODEL |
| `magnetar.stages.simulate` | `run(task_dir, sample, image, board=board)` → `metrics` | 精度对分（优先板端 ax_run_model，回退 pulsar2 run） |
| `magnetar.stages.sdk_gen` | `run_mobilenet_python()`, `run_mobilenet_cpp()`；`run_generic_python(task_dir)`, `run_generic_cpp(task_dir)` | 生成 Python/C++ SDK（通用版基于 model_meta + model_flow） |
| `magnetar.stages.runonboard` | `run(task_dir, sample, hw, pwd)` → `metrics` | 板端部署验证 |
| `magnetar.stages.package` | `assemble(task_dir, metrics, image)` → `pkg`, `self_test(pkg)` → `result` | 组装面向小白的交付包，含一键脚本 + README + 自测 |
| `magnetar.stages.publish` | `publish(pkg, target, name, token, org, model)` → `result` | 发布到 GitHub（源码）或 HuggingFace（预编译） |

非 MobileNet 模型：优先使用 `magnetar.stages.export.run_generic` /
`scripts/export_onnx.py` 通用导出器（load 脚本约定 `build()` 返回 `(model, example_inputs)`），
导出失败时依据 `export/export_report.md` 的诊断报告决定人工处理方向；确需手写导出逻辑时
再自行实现并正确填写 `model_meta.json`。

## 执行流程

严格按以下顺序推进 10 阶段，不可跳过。每阶段完成后更新 `task.md` 和 `analysis.md`。

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
- PUBLISH 需用户确认发布目标、仓库名、凭据

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

### PUBLISH 发布
- 进入 PUBLISH 阶段时暂停，询问用户：发布到哪里（GitHub/HuggingFace）、仓库名、凭据位置
- GitHub：推送完整源码 + model_convert（客户可复现编译流程）
- HuggingFace：仅上传预编译模型 + SDK 产物（客户直接用），不含 model_convert/ 复现脚本
- HF README 自动添加 YAML frontmatter
- 凭据通过 GITHUB_TOKEN / HF_TOKEN 环境变量或 .magnetarrc 提供

## 验证期望

- ONNX 导出可复现，Torch/ONNX 对分 cosine ≥ 0.99
- Pulsar2 配置 `highest_mix_precision` 为 false
- Python SDK `import <sdk>` 通过，默认 `AxEngineExecutionProvider`
- C++ SDK cmake configure 通过
- `ax_run_model` 仅用于 smoke check，不能替代 SDK 验证
- PACKAGE 产出独立 git 项目，板端自验证通过
- 端到端 NPU 跑通后，发布包 SDK 不含 onnxruntime/torch/transformers 回退（NPU 专用版）

## 爱芯开发知识

完整资源清单见 `docs/ax-knowledge.md`（仅查证 URL/版本时按需读取，不随每轮全量加载）。

## Token 效率约定

本工作流面向长流程（10 阶段 + 重试 + 回退），上下文是稀缺资源，遵守以下约定：

- 大日志只读尾部 + 关键指标，完整日志落盘不读入
- 进度/恢复读 `.magnetar-state.json`，不读 task.md 全文
- 禁止读取二进制产物（.npy/.bin/.axmodel/.onnx/.pt）
- compile 日志用 `summarize_compile_log()` 取指标，不读全文
- 查 `issues/` 先读 `INDEX.md`，只读命中的文件
- 对齐按批确认，缺失项一次列清单带推荐答案
- 优先 `stages/*.py` 现成函数与 `export_onnx.py` 通用导出器
- 每阶段一句话更新 `task.md`/`analysis.md`，详细报告只落盘

完整约定见 `.codex/skills/magnetar/SKILL.md` 与 `docs/ax-knowledge.md`。
