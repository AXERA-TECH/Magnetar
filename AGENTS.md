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
| `magnetar.board_util` | `select_board()`, `ssh()`, `scp_to()`, `scp_from()`, `ensure_remote_infer()`, `port_open()` | AX 板端操作（上板前确保 ax-remote-infer 已装，18500 端口可发现板子） |
| `magnetar.stages.init` | `run(config)` → `task_dir` | 创建 TASK_DIR 结构 |
| `magnetar.stages.acquire` | `run(task_dir, source)`；`write_model_flow(task_dir, flow)` | 获取模型到 origin/ 并记录运行流程 |
| `magnetar.stages.export` | `run_mobilenet(task_dir)` → `sample`；`run_generic(task_dir, ...)` → `result` | MobileNet 专用 / 任意模型通用导出（先简后繁自动降级） |
| `magnetar.stages.toolchain` | `run()` → `pulsar_image` | 验证 Pulsar2 Docker 可用 |
| `magnetar.stages.compile` | `run(task_dir, target_hw, image)` | Pulsar2 编译 AXMODEL |
| `magnetar.stages.simulate` | `run(task_dir, sample, image, board=board, target_hw=...)` → `metrics` | 精度对分（有板优先上板 ax_run_model，无板才回退 pulsar2 run） |
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

SIMULATE 有板必上板（ax_run_model 秒级），pulsar2 run 仅无板/板端失败时回退；BOARD 未配置时先 `select_board()` 找空闲板，找不到才用仿真。

## STOP 点

必须暂停等待用户确认：
- `SOURCE`、`TARGET_HARDWARE` 未提供
- ONNX 与原模型对分失败（cosine < 0.99）
- 模型含动态 shape 且静态化失败
- Pulsar2 不可用
- 编译失败需改 ONNX → 退回 EXPORT
- SIMULATE 精度不达标（先查 `issues/`；INT8/U16/混合精度全试过仍不过时，STOP 前先向用户提议上 QAT）
- 需要私有凭据
- PUBLISH 需用户确认发布目标、仓库名、凭据

BOARD 缺失不是 STOP：SIMULATE 先用 `select_board()` 找空闲板上板，找不到才回退 pulsar2 run；RUNONBOARD 无板自动跳过。

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

## 模型获取

- 模型下载/获取优先 ModelScope（国内 CDN 快，公开模型无需额外凭据），HuggingFace 仅作回退
- HuggingFace 下载慢时走镜像：`HF_ENDPOINT=https://hf-mirror.com`；大权重可用 ModelScope CDN 分片并行下载（参考 `issues/013_moss-tts-realtime_ax650_pipeline_pitfalls.md`）
- SOURCE 支持 ModelScope / HuggingFace / Git URL / HTTP URL / 本地文件或目录

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
校准集尽量用真实业务数据（真实输入/中间特征），随机/扰动数据仅兜底——可能在标定集上好看，真实业务上崩；
真实数据入口：`run_generic(calibration_data=...)` 或 `scripts/export_onnx.py --calib-dir`。

INT8 / U16 / 混合精度（layer_configs、SmoothQuant、Brecq、Percentile 等）全部尝试仍 cosine < 0.99 时，
STOP 前先向用户提议上 QAT（量化感知训练）：
- QAT 框架必须使用官方 `AXERA-TECH/QAT.axera`，不得改用其他 QAT 实现（保证与 Pulsar2 编译链路兼容）
- 优先 QAT→QDQ ONNX 通道：Pulsar2 的 PTQ 会重新计算 scale，把 QAT 训练收益归零（见 `issues/piper_tts_experience.md` §2）
- QAT.axera 基础 fake-quant 链路可用，但训练稳定性需先做 toy sanity（见 `issues/melotts_pipeline_issues.md` QAT 追加记录）
- QAT 需要训练数据和训练时间，成本高；用户确认后才进入，通常退回 EXPORT 重新导出 QDQ ONNX

### 编译
ONNX 必须静态 shape。编译前用 ONNX Runtime 验证。

### 输入/输出格式（成功案例固化）
- 校准数据、pulsar2 run、ax_run_model、axengine 输入格式一律按 `docs/input-format-cheatsheet.md`，禁止反复试格式
- 代码层单一来源：`magnetar/io_format.py`；`python magnetar/pulsar2_ref.py --cases` 打印成功案例
- 高频坑：U8 校准 `calibration_std=255`、Numpy 校准 npy 带 batch 维、`tensor_name` 与 ONNX 输入名一致、bin 文件名必须等于 tensor 名

### 板端 ax-remote-infer
- 上板（SIMULATE 板端通道 / RUNONBOARD）前检查 TCP 18500：daemon 已跑则直接复用；未装则用官方 release 的 `remote_install.sh` 静默安装（缓存 `~/.cache/magnetar/ax-remote-infer`）
- 装好后可通过扫描 18500 端口发现板子：`select_board()` 在 dashboard 不可用/无空闲板时回退扫描 `MAGNETAR_SCAN_SUBNET`（默认 dashboard 所在 /24）

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
