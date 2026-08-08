---
name: magnetar
description: Convert remote or local AI models into AXera AXMODEL packages with Python and C++ SDKs for customer delivery.
---

# Magnetar

始终用中文沟通。完整工作流和爱芯开发知识见 `AGENTS.md`。

## 执行

按顺序推进 10 阶段，每阶段读取对应 `hidden/<stage>/SKILL.md`：

```
ACQUIRE → INIT → EXPORT → TOOLCHAIN → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE → PUBLISH
```

- 各阶段优先调用 `magnetar/stages/*.py` 工具函数
- 遇到 STOP 点暂停等用户确认
- BOARD 未配置时 RUNONBOARD 自动跳过
- 回退/重试/循环逻辑由 `workflows/magnetar.yaml` 状态机控制

## 模型路由（model_route gate）

INIT 之后、EXPORT 之前，用 `magnetar.stages.llm.classify(origin, ...)` 判定模型类型：

- `route=general`：原通用路径（ONNX → pulsar2 build → 对分仿真）。
- `route=llm`（自回归 / 类 LLM，如 Qwen、Llama、MiniCPM、GPT、SmolLM、DeepSeek，
  或含 LLM 骨干的 TTS）：改用 **ax-llm** 路径——
  - EXPORT：不导出 ONNX，验证 HF 权重可推理 + 生成可复现 `export/llm_build.sh`；
  - COMPILE：`pulsar2 llm_build2`（Pulsar2 ≥ 6.0）直接编译权重为逐层 axmodel +
    post axmodel + bf16 embedding（自带逐层 decode/prefill cosine 校验），
    ax-llm-build `embed_process.sh` 处理 embedding，组装 `compile/llm_model_dir/`
    （config.json + tokenizer + axmodel + post_config.json）；
  - SIMULATE：有板 → 装 axllm + `axllm serve` + OpenAI 兼容接口语义验证；
    无板 → `llm_build2 --check_level 2` 自带校验；
  - SDK-GEN：Python = OpenAI 兼容 HTTP 客户端（依赖仅 requests）；
  - RUNONBOARD：板端 `install_axllm` + `serve_axllm` + `validate_chat`；
  - PACKAGE：`models/` 为 axllm 模型目录，model_convert 含可复现 llm_build2。
- `hybrid`（如 MOSS-TTS、NeuTTS-2E 等含 LLM/AR 子模型的组合模型）：route=llm，
  但需先确认 LLM/AR 子模型拆分方案；无法确认 → STOP 问用户。

LLM 路由失败回退：`pulsar2 llm_build2` 不支持该架构/head_dim/算子 → 回退 EXPORT 调整
（weight_type、context 参数、hybrid 拆分），仍失败 STOP 由用户决定是否回退通用 ONNX 路径；
逐层 cosine < 0.99 → 回退 COMPILE（s8→s4 / bf16→fp16 / 调 context），仍失败 STOP 提议 QAT。

## 阶段速查表

常规流程按下表推进；只有出现异常/STOP 时才深入读取对应 `hidden/<stage>/SKILL.md`，
正常路径不再逐个加载全部 hidden 技能以节省上下文。

**状态与进度一律读 `TASK_DIR/.magnetar-state.json`**（阶段/产物/一句话摘要），
不读 task.md 全文；task.md 仅作人类可读审计。

| 阶段 | 执行函数 | 验证要点 | STOP |
|------|----------|----------|------|
| INIT | `stages.init.run(config)` | 9 个子目录 + task.md/analysis.md/config.json | 无 |
| ACQUIRE | `stages.acquire.run(task_dir, source)` | origin/ 有文件 + ACQUIRE_REPORT.md + route_hint | SOURCE 无效 / 私有凭据缺失 |
| MODEL-ROUTE | `stages.llm.classify(origin, ...)` | route=llm / general；hybrid 需确认拆分 | hybrid 拆分方案无法确认 |
| EXPORT | general：`run_mobilenet`/`run_generic`；llm：验证权重 + `llm_build.sh` | general 静态 ONNX + cosine≥0.99；llm 权重可推理 | 对分失败 / 动态 shape 静态化失败 / llm_build2 不支持需定回退方向 |
| TOOLCHAIN | `stages.toolchain.run()`；llm：`ensure_axllm_build_tools` | pulsar2 可用（llm 需 llm_build2）+ BSP | Pulsar2 / BSP 不可获取 |
| COMPILE | general：`stages.compile.run`；llm：`stages.llm.llm_build` | general axmodel 非空；llm 模型目录完整 + 逐层 cosine≥0.99 | 编译失败需改 ONNX/参数 → 退回 EXPORT |
| SIMULATE | `stages.simulate.run(...)`（llm：`install_axllm`+`serve_axllm`+`validate_chat`） | general cosine≥0.99；llm 逐层 cosine min≥0.99 + 有板语义验证 | 精度不达标 → 先查 `issues/INDEX.md` |
| SDK-GEN | `run_generic_python/cpp`；llm：OpenAI 兼容 HTTP 客户端 | `import <sdk>` 通过 + cmake configure 通过（llm 依赖仅 requests） | 无 |
| RUNONBOARD | `stages.runonboard.run(...)`；llm：`serve_axllm`+`validate_chat` | Python/C++ 板端验证 + TTFT/token 速率/内存 | 无（BOARD 缺失自动跳过） |
| PACKAGE | `stages.package.assemble` + `self_test` | self_test 通过 + README 无占位符 + 可独立发布 | 无 |
| PUBLISH | `stages.publish.publish(...)` | 返回 repo/model URL | 询问发布目标、仓库名、凭据 |

## Token 效率约定

- 大日志（compile.log、pulsar2_run.log、SSH 输出）只读尾部 `tail -100` 与关键指标，完整日志落盘不读入
- docker/SSH 大输出默认截断（`magnetar.docker_util.run` / `board_util.ssh` 的 max_tail），完整日志只落盘，异常只带尾部
- 编译后调用 `magnetar.stages.compile.summarize_compile_log(task_dir)` 取 MACs/大小/错误行，禁止读 compile.log 全文
- **禁止读取二进制产物**（.npy/.bin/.axmodel/.onnx/.pt 等）；需要 shape 用 numpy 查询，需要指标用摘要函数
- 查 `issues/` 先读 `issues/INDEX.md`，只读命中的文件
- 每阶段只用一句话结论更新 `task.md`/`analysis.md`，详细报告落盘
- 每阶段只读一次对应 hidden SKILL.md，不重复通读 `workflows/magnetar.yaml`
- 需求对齐先读 `.magnetarrc` 并探索仓库，缺失项一次性列清单带推荐答案确认
- 汇报/答复只给结论 + 指标，不贴大段日志
- 详细爱芯资源见 `docs/ax-knowledge.md`，按需读取

## 断点续跑

中断后恢复：新会话先读 `TASK_DIR/.magnetar-state.json`，从 `stage` 字段所在阶段继续；
只读当前阶段产物路径，不重放历史对话。`status=blocked` 时先看对应阶段报告/诊断再重试。

## 配置

读取 `.magnetarrc`（shell 风格 key=value），环境变量可覆盖。详见 `.magnetarrc.example`。
INIT 后各阶段读 `TASK_DIR/config.json`（`magnetar.config.load_task_config(task_dir)`），
任务参数以 INIT 快照为准，`.magnetarrc` 仅作公共默认，多任务并发互不影响。
