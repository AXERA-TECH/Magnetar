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
| `magnetar.errors` | `MagnetarError`/`classify_error()` | 类型化错误码注册表（与 `magnetar.yaml` retry_on 对齐，测试强制） |
| `magnetar.stages.events` | `log_event()`/`log_error()` | 追加式事件日志 `.magnetar-events.jsonl`（可回放审计流，`mark_stage` 自动写） |
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
| `magnetar.stages.llm` | `classify(origin, ...)` → 路由；`llm_build(task_dir, input, chip, image, ...)` → `model_dir`；`install_axllm(board)` / `serve_axllm(board, model_dir)` / `validate_chat(api_url, ...)` | LLM/自回归模型路由与 ax-llm 部署（llm_build2 编译 + axllm 板端 serve/验证） |

非 MobileNet 模型：优先使用 `magnetar.stages.export.run_generic` /
`scripts/export_onnx.py` 通用导出器（load 脚本约定 `build()` 返回 `(model, example_inputs)`），
导出失败时依据 `export/export_report.md` 的诊断报告决定人工处理方向；确需手写导出逻辑时
再自行实现并正确填写 `model_meta.json`。

LLM/自回归模型（route=llm）：不走通用 ONNX 路径，改用 ax-llm——
`pulsar2 llm_build2`（Pulsar2 ≥ 6.0）直接编译 HF 权重 → `compile/llm_model_dir/`
（逐层 axmodel + post axmodel + bf16 embedding + tokenizer + axllm config.json），
板端用 `axllm run/serve`（AXERA-TECH/ax-llm，axllm 分支）；SDK 为 OpenAI 兼容
HTTP 客户端（Python 依赖仅 requests）。判定函数：`magnetar.stages.llm.classify`
（config architectures/model_type、pipeline_tag、model_flow task、模型名）。
hybrid 组合模型（MOSS-TTS、NeuTTS-2E 等）需先确认 LLM/AR 子模型拆分方案。

## 执行流程

严格按以下顺序推进 10 阶段，不可跳过。每阶段完成后更新 `task.md` 和 `analysis.md`。
INIT 后先过 `model_route` gate：route=llm 时 EXPORT/COMPILE/SIMULATE/SDK-GEN/
RUNONBOARD/PACKAGE 按 ax-llm 分支执行（详见 `.codex/skills/magnetar/SKILL.md` 路由节）。

状态机（回退/重试/循环）由 `workflows/magnetar.yaml` 控制。日常执行按
`workflows/magnetar-summary.md`（全局读一次）+ `workflows/steps/<阶段>.md`（每阶段读对应片段），
仅状态机诊断/排障时才读 yaml 全文。

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

多任务并发隔离约定：
- `.magnetarrc` 只放公共默认（凭据/工具链/镜像/行为选项），任务参数（SOURCE/TARGET_HARDWARE/MODEL_NAME/BOARD/TASK_DIR）不要在里面反复改写
- 每个任务 INIT 时把任务参数固化到 `TASK_DIR/config.json`；之后各阶段一律用 `magnetar.config.load_task_config(task_dir)` 读取，禁止并发任务互相改写 `.magnetarrc`

## 目录约定

```
TASK_DIR/
  origin/       export/       compile/       simulate/
  sdk/python/   sdk/cpp/      runonboard/    package/    cache/
  task.md       analysis.md   .magnetar-state.json   .magnetar-events.jsonl
```

产物不得污染原始模型工程。
`mark_stage` 每阶段收尾自动追加 stage/artifact/metric 事件到 `.magnetar-events.jsonl`；
错误统一抛 `MagnetarError(code)`，新错误码先登记 `magnetar/errors.py` 再进 yaml retry_on。

## 模型获取

- 模型下载/获取优先 ModelScope（国内 CDN 快，公开模型无需额外凭据），HuggingFace 仅作回退
- 涉及 HF 的任何东西（模型权重、Pulsar2、ModelZoo 等）先查
  ModelScope 有没有：`magnetar.net_util.modelscope_available("<org>/<name>")` 探测
  （HF repo id 与 ModelScope 约定一致，如 AXERA-TECH/Pulsar2 两侧都有），有则优先
  ModelScope 下载，没有才回退 HF/hf-mirror
- HF 大文件（权重等）下载默认用 hf-mirror 的 hfd 工具：
  `scripts/download_hf.sh <org>/<name> --local-dir origin/<name> -x 8`
  （自动缓存 `~/.cache/magnetar/hfd.sh`，端点默认 hf-mirror，aria2c 多线程；
  小文件如 tokenizer.json 仍可直接单线走 HF_ENDPOINT）
- 默认国内镜像：HuggingFace `HF_ENDPOINT=https://hf-mirror.com`；GitHub 克隆/下载经
  `GH_PROXY=https://gh-proxy.com`；uv/pip 默认 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`
  （海外用户可在 `.magnetarrc` 置空字符串禁用，恢复直连）
- 大权重可用 ModelScope CDN 分片并行下载（参考 `issues/013_moss-tts-realtime_ax650_pipeline_pitfalls.md`）
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
STOP 前先向用户提议上 QAT（量化感知训练）；QAT 的框架选型/实现通道/注意事项见
`docs/ax-knowledge.md` §QAT（官方 QAT.axera、QAT→QDQ 通道、toy sanity、成本与进入条件）。

### 环境复用（避免重复装大包）
- 大包只装一次：`python -m magnetar.env_util base`（默认 `~/.cache/magnetar/base-venv`，
  `MAGNETAR_BASE_VENV` 可覆盖；依赖清单 `requirements/base.txt` 变化才自动重建）
- 每个任务用 `magnetar.env_util.create_task_venv(task_dir, extra_packages=...)` 建薄 venv
  （.pth 链接 base，任务本地包优先），路径固化到 TASK_DIR/config.json 的 VENV_PATH；
  禁止每个模型重建完整 torch/transformers 大环境
- 后续阶段解释器统一取 `magnetar.env_util.resolve_task_python(task_dir)`
- BSP/交叉工具链也走公共目录：`magnetar.bsp_util.ensure_bsp(target_hw, cfg)` 自动
  下载/解压到 `MAGNETAR_BSP_HOME`（默认 `~/.cache/magnetar/bsp`）；SDK/runtime
  下载地址按芯片从 ax-pipeline `scripts/build_common.sh` 解析（`MSP_URL_DEFAULT` /
  `TOOLCHAIN_URL_DEFAULT`；AX650 为 msp_50_3.10.2.zip + Arm GNU 9.2 aarch64，
  AX630C / AX620Q（AX620E NPU）为 msp_20e + build_common.sh 对应编译器
  （AX620Q 为 ax620q_bsp_sdk uclibc）；`CXX_BSP_URL`/`CXX_TOOLCHAIN_URL` 可覆盖，
  `BUILD_COMMON_SH_URL` 可换清单源），探测 `AX_RUNTIME_ROOT` 与交叉编译器；
  C++ SDK 编译一律
  `magnetar.bsp_util.build_cpp_sdk(task_dir, cfg)`，禁止再手动找 ax_engine 头文件/库

### 编译
ONNX 必须静态 shape。编译前用 ONNX Runtime 验证。

### LLM / 自回归模型（ax-llm）
- 入口：`pulsar2 llm_build2`（Pulsar2 ≥ 6.0，支持 AX650A/N、AX630C，其他芯片以
  `--chip` 支持与 ax-llm 实际验证为准）；产物逐层 axmodel + post axmodel +
  bf16 embedding，自带逐层 decode/prefill cosine 校验。
- 板端运行：AXERA-TECH/ax-llm `axllm` 分支（`axllm run <model_dir>` /
  `axllm serve <model_dir> --port 8000`，OpenAI 兼容 API）；安装
  `curl -fsSL https://raw.githubusercontent.com/AXERA-TECH/ax-llm/axllm/install.sh | bash`。
- 辅助工具：AXERA-TECH/ax-llm-build（embed_process.sh 提取/转换 embedding；
  config/*.json 为 llm_build 配置样例）。
- axllm 模型目录 config.json 必填字段：model_name、tokenizer_type、
  url_tokenizer_model（本地 tokenizer 文件）、template_filename_axmodel（含 %d）、
  axmodel_num、filename_post_axmodel、filename_tokens_embed、
  tokens_embed_num、tokens_embed_size。
- 精度验收：逐层 cosine min ≥ 0.99 + 板端语义验证（≥3 组 prompt 全非空）；
  不达标先调 weight_type（s8→s4）/hidden_state_type/context，仍失败 STOP 提议 QAT。

### 输入/输出格式（成功案例固化）
- 校准数据、pulsar2 run、ax_run_model、axengine 输入格式一律按 `docs/input-format-cheatsheet.md`，禁止反复试格式
- 代码层单一来源：`magnetar/io_format.py`；`python magnetar/pulsar2_ref.py --cases` 打印成功案例
- 高频坑：U8 校准 `calibration_std=255`、Numpy 校准 npy 带 batch 维、`tensor_name` 与 ONNX 输入名一致、bin 文件名必须等于 tensor 名

### 板端 ax-remote-infer
- 上板（SIMULATE 板端通道 / RUNONBOARD）前检查 TCP 18500：daemon 已跑则直接复用；未装则用官方 release 的 `remote_install.sh` 静默安装（缓存 `~/.cache/magnetar/ax-remote-infer`）
- release 下载默认经 `GH_PROXY`（`AX_REMOTE_INFER_URL` 可覆盖）
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
- SDK 前后处理对齐原版模型（`model_flow.json` 的 preprocess/postprocess 来自原版管线，ACQUIRE 阶段验证过），调用方式尽量对齐原版入口（`sdk_interface` 记录入参顺序/输入格式/输出结构），禁止为省事改成直通/自定义
- `ax_run_model` 仅用于 smoke check，不能替代 SDK 验证
- PACKAGE 产出独立 git 项目，板端自验证通过
- 交付包 Python/C++ 尽量减少依赖：端到端 NPU 跑通后 SDK 仅依赖 numpy + pyaxengine，
  不含 onnxruntime/torch/transformers 等回退；CPU fallback 尽量不做，能端到端 NPU 就端到端
  （RUNONBOARD 通过即强制 NPU-only 交付，package 装配时会校验无回退依赖）

## 爱芯开发知识

完整资源清单见 `docs/ax-knowledge.md`（仅查证 URL/版本时按需读取，不随每轮全量加载；
SDK/BSP 下载地址除外——按芯片查 ax-pipeline `build_common.sh`，ax-knowledge 不再收录）。

## Token 效率约定

本工作流面向长流程（10 阶段 + 重试 + 回退），上下文是稀缺资源，遵守以下约定：

- 大日志只读尾部 + 关键指标，完整日志落盘不读入
- docker/SSH 大输出默认截断返回尾部（≤400 行），完整日志落盘（compile.log / pulsar2_run.log），异常也只带尾部 + 日志路径
- shell 检索用 `rg -l`/`head`/`tail` 限长输出，禁止整段 dump
- 进度/恢复读 `.magnetar-state.json`，不读 task.md 全文
- 禁止读取二进制产物（.npy/.bin/.axmodel/.onnx/.pt）
- compile 日志用 `summarize_compile_log()` 取指标，不读全文
- 查 `issues/` 先读 `INDEX.md`，只读命中的文件
- 每阶段只读一次对应 hidden SKILL.md 与 `workflows/steps/<阶段>.md`，全局只读一次 `workflows/magnetar-summary.md`，不重复通读 `workflows/magnetar.yaml` 全文
- 对齐按批确认，缺失项一次列清单带推荐答案
- 优先 `stages/*.py` 现成函数与 `export_onnx.py` 通用导出器
- 每阶段一句话更新 `task.md`/`analysis.md`，详细报告只落盘
- 汇报/答复只给结论 + 指标，不贴大段日志

完整约定见 `.codex/skills/magnetar/SKILL.md` 与 `docs/ax-knowledge.md`。
