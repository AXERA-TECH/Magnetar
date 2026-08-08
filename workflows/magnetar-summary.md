# Magnetar 工作流摘要（日常按此执行，不用通读 yaml 全文）

> 权威状态机：`workflows/magnetar.yaml`（仅状态机诊断/排障时才读全文）。
> 日常执行：本摘要（全局只读一次）+ `workflows/steps/<阶段>.md`（每阶段只读对应片段）。

## 阶段顺序

`INIT → ACQUIRE → EXPORT → TOOLCHAIN → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE → PUBLISH`

| 阶段 | yaml 步骤 id | 片段 | hidden skill |
|------|--------------|------|--------------|
| INIT | `init` | steps/init.md | hidden/init |
| ACQUIRE | `acquire` | steps/acquire.md | hidden/acquire |
| EXPORT | `export` | steps/export.md | hidden/export |
| TOOLCHAIN | `toolchain` | steps/toolchain.md | hidden/toolchain |
| COMPILE | `compile` | steps/compile.md | hidden/compile |
| SIMULATE | `simulate` | steps/simulate.md | hidden/simulate |
| SDK-GEN | `sdk_gen` | steps/sdk-gen.md | hidden/sdk-gen |
| RUNONBOARD | `runonboard` | steps/runonboard.md | hidden/runonboard |
| PACKAGE | `package` | steps/package.md | hidden/package |
| PUBLISH | `publish` | steps/publish.md | hidden/publish |

## 模型路由（新增 gate：model_route）

ACQUIRE/INIT 之后、EXPORT 之前，用 `magnetar.stages.llm.classify(origin, ...)` 判定：

- `route=general`：原通用路径（ONNX 导出 → pulsar2 build → 对分仿真）。
- `route=llm`（自回归 / 类 LLM，如 Qwen、Llama、MiniCPM、GPT、SmolLM、含 LLM 骨干的
  TTS）：改用 ax-llm 路径——
  - EXPORT：不导出 ONNX，验证 HF 权重可推理并生成可复现 `export/llm_build.sh`；
  - COMPILE：`pulsar2 llm_build2`（Pulsar2 ≥ 6.0）直接编译权重 → 逐层 axmodel +
    post axmodel + bf16 embedding（自带逐层 decode/prefill cosine 校验），
    再用 ax-llm-build `embed_process.sh` 处理 embedding，生成
    `compile/llm_model_dir/`（config.json + tokenizer + *.axmodel）；
  - SIMULATE：有板 → 装 axllm + `axllm serve` + OpenAI 兼容接口语义验证；
    无板 → 回退 `llm_build2 --check_level 2` 自带校验（逐层 cosine），语义验证留给 RUNONBOARD；
  - SDK-GEN：Python = OpenAI 兼容 HTTP 客户端（依赖仅 requests），C++ = HTTP 客户端；
  - RUNONBOARD：板端安装 axllm（`curl -fsSL .../ax-llm/axllm/install.sh | bash`），
    serve 模型目录，记录 TTFT / token 速率 / 内存；
  - PACKAGE：`models/` 为 axllm 模型目录，model_convert 提供可复现 llm_build2 命令。
- `hybrid`（如 MOSS-TTS、NeuTTS-2E 等含 LLM/AR 子模型的组合模型）：route=llm，
  但需先确认 LLM/AR 子模型拆分方案（无法确认 → STOP 问用户）。

LLM 路由失败回退：llm_build2 不支持该架构/head_dim/算子 → 回退 EXPORT 调整
（weight_type、context 参数、hybrid 拆分），仍失败 STOP 由用户决定是否回退通用 ONNX 路径；
逐层 cosine < 0.99 → 回退 COMPILE（s8→s4 / bf16→fp16 / 调 context），仍失败 STOP 提议 QAT。

## 关键 gate

- `requirements_gate`：SOURCE / TARGET_HARDWARE 必填；BOARD 可选（缺失跳过 RUNONBOARD）
- `dry_run_check`：MODE=dry-run 时展示计划即 STOP，需切 MODE=full
- `model_route`：LLM/AR 模型路由判定；hybrid 拆分方案需用户确认
- `export_valid`：general 静态 shape + ORT 可加载 + Torch/ONNX 对分通过；
  llm 验证权重可推理 + 生成 llm_build.sh
- `accuracy_gate`：general cosine ≥ 0.99；llm 逐层 cosine min ≥ 0.99 + 有板时语义验证
- `llm_route_acceptance`：llm 模型目录完整（config.json/tokenizer/逐层/post axmodel）
  + compile_cosine.min ≥ 0.99 + 有板时 ≥3 组 prompt 验证
- `package_validation`：self_test 全过（README → setup.sh → run.sh），失败修脚本重试 ≤3 次
- `publish_gate`：目标/仓库名/凭据确认 + URL 可访问 + 无凭据泄漏

## STOP 点（等用户）

SOURCE/TARGET_HARDWARE 缺失、对分失败、动态 shape 静态化失败、Pulsar2 不可用、
编译失败需改 ONNX（回退 EXPORT）、SIMULATE 精度不达标无已知修复（先提议 QAT）、
hybrid 模型拆分方案无法确认、llm_build2 不支持该架构需决定回退方向、私有凭据、
PUBLISH 目标/仓库/凭据。

## 回退/重试

- COMPILE 失败 → 回退 EXPORT（调导出策略）
- SIMULATE 工具失败 / accuracy 不达标 → 回退 COMPILE（调量化配置）
- LLM 路由：llm_build2 失败 → 回退 EXPORT；逐层 cosine < 0.99 → 回退 COMPILE
  （s8→s4 / bf16→fp16 / context）；均失败 → STOP 提议 QAT 或回退通用路径
- PACKAGE 校验失败 → 修脚本重打包，≤3 次
- PUBLISH 失败 → 修凭据/仓库重试，≤2 次
- 总尝试上限：3 次；超出转人工

## 常用输入（yaml inputs 段，环境变量可覆盖）

SOURCE、TARGET_HARDWARE、MODEL_NAME、TASK_DIR、HF_TOKEN、HF_ENDPOINT、
PULSAR2_IMAGE、PULSAR2_BIN、PULSAR2_HF_REPO、BOARD、BOARD_PASSWORD、
AUTO_APPROVE、MODE、AX_LLM_REPO、AX_LLM_BRANCH、AX_LLM_BUILD_REPO、
LLM_MAX_CONTEXT、LLM_PREFILL_LEN、LLM_PREFILL_STEP_SIZE、LLM_WEIGHT_TYPE、
LLM_HIDDEN_STATE_TYPE。

## 完成条件

requirement.acceptance 的 checks + required_artifacts 全过；RUNONBOARD 已尝试
（有板执行、无板跳过）；publish URL 与目标记录在 task.md。
