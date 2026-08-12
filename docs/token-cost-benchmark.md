# Token 用量与费用实测记录（2026-08-12）

> 目的：给"用 AI Agent 跑 Magnetar 转换到底花多少 token / 多少钱 / 多久"一个真实账本，
> 用于团队推广与成本预期。两个模型均从**原始来源**完整跑通（不复用 `issues/` 或
> HF 已转换产物），未配 BOARD（RUNONBOARD 自动跳过），不进入 PUBLISH。

## 1. 实测环境（本机配置）

| 项 | 值 |
|----|----|
| 系统 | Ubuntu 22.04.5 LTS（kernel 6.8.0-124-generic），x86_64 |
| CPU | 96 核 Intel Xeon Gold 6336Y @ 2.40GHz |
| 内存 | 503 GB |
| 磁盘 | /data 约 17 TB 可用 |
| GPU | 无 |
| 编译环境 | Docker + Pulsar2 7.0 |
| Agent | codex-cli 0.142.2（`codex exec`，独立会话）|
| 会话模型 | deepseek-v4-flash（api.deepseek.com，Responses API，reasoning=high）|

## 2. 实测结果汇总

| 模型 | 路径 | 时长 | 输入 tokens | 缓存命中 | 输出 tokens | 估算费用 |
|------|------|------|-------------|-----------|-------------|----------|
| yolov8n | 通用（ONNX → INT8 → pulsar2 run 仿真）| 14 分钟 | 6,865,861 | 98.8% | 50,209 | ≈ ¥0.32 |
| Qwen3-0.6B | ax-llm（llm_build2 s8/bf16，无板自带校验）| 5.1 小时 | 27,148,037 | 99.5% | 99,429 | ≈ ¥0.87 |

费用估算口径（DeepSeek 官方平峰价，2026-08-12）：

```
费用 = (输入 - 缓存命中)/1M × ¥1 + 缓存命中/1M × ¥0.02 + 输出/1M × ¥2
```

工作日 9:00–12:00、14:00–18:00 为高峰时段，价格翻倍；两次实测均在凌晨平峰时段。
DeepSeek 已于 2026-08 预告整体上调 API 价格，本表随时可能失效；精确账单以
DeepSeek 平台为准。

## 3. yolov8n 实测明细（通用路径）

- 任务目录：`todos/work/yolov8n-ax650`
- SOURCE：`https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt`
  （6.2MB，从 ultralytics 官方下载）
- 会话：`~/.codex/sessions/2026/08/12/rollout-2026-08-12T01-18-43-019ff1d5-6c1c-7da3-95e1-d931d2edb691.jsonl`
- 时长：01:18:44 → 01:32:41（CST），共 13 分 57 秒
- token：输入 6,865,861（缓存命中 6,782,080，98.8%），输出 50,209，合计 6,916,070
- 费用：≈ ¥0.32

| 阶段 | 结果 |
|------|------|
| INIT / ACQUIRE | yolov8n.pt 下载并验证（bus.jpg 原版推理 6 dets），model_flow 已记录 |
| MODEL-ROUTE | route=general（走通用 ONNX 路径）|
| EXPORT | ONNX 1×3×640×640 → output0 1×84×8400，Torch/ONNX cosine=1.000000；4 组真实校准样本（bus/zidane，含翻转）|
| TOOLCHAIN | pulsar2:7.0（commit 6b1bcdf8）可用 |
| COMPILE | INT8 MinMax，model.axmodel 3405.6 KB，MACs≈4.37G，highest_mix_precision=false |
| SIMULATE | 无板走 pulsar2 run 仿真：3 样本 cosine=0.99916±0.00027，MAE=0.26±0.06，INT8 一次通过 |
| SDK-GEN | Python SDK import/example 通过（修复 NMS bug）；C++ cmake configure 通过 |
| RUNONBOARD | 跳过（未配 BOARD）|
| PACKAGE | self_test 通过（setup.sh + run.sh，bus.jpg 检出 5 目标），交付包 28.0 MB |
| PUBLISH | 未进入 |

## 4. Qwen3-0.6B 实测明细（ax-llm 路径）

- 任务目录：`todos/work/20260812_012012-Qwen3-0.6B`
- SOURCE：`Qwen/Qwen3-0.6B`（ModelScope 下载，1.50G safetensors，11 文件）
- 会话：`~/.codex/sessions/2026/08/12/rollout-2026-08-12T01-19-17-019ff1d5-f0b4-7850-870c-acd544c94eb0.jsonl`
- 时长：01:19:18 → 06:25:54（CST），共 306.6 分钟（5.11 小时）
- token：输入 27,148,037（缓存命中 27,013,376，99.5%），输出 99,429，合计 27,247,466
- 费用：≈ ¥0.87

| 阶段 | 结果 |
|------|------|
| INIT / ACQUIRE | ModelScope 下载完成，model_flow/route_hint 已写 |
| MODEL-ROUTE | route=llm（Qwen3ForCausalLM / qwen3 / text-generation，非 hybrid）|
| EXPORT(llm) | 权重 greedy 推理通过（1+1=2），qwen3_tokenizer.txt 转换完成 |
| TOOLCHAIN | pulsar2:7.0 + 永久 license，llm_build2 可用 |
| COMPILE | llm_build2 s8/bf16，max_context=1024，prefill 512/128；28 层 + post + bf16 embedding；model_dir 34 文件（约 990MB）|
| SIMULATE | 无板回退 llm_build2 自带校验：decode cos=1.0、prefill cos=1.0（min=1.0 ≥ 0.99）|
| SDK-GEN | Python（requests HTTP 客户端）import 通过；C++（socket）cmake configure/build 通过 |
| RUNONBOARD | 跳过（未配 BOARD，语义验证留待上板）|
| PACKAGE | 交付包约 991MB；self_test 通过（setup/import/cmake；run.sh 板端前置）|
| PUBLISH | 未进入 |

### 本次唯一的流程回退（真实试错成本，已按规则处理一次）

首轮 `llm_build2 --check_level 2` 的逐位生成校验（“1+1”）在 max_context=1024 下
按解码位置逐 token 推进：**4.5 小时仅完成 19 个位置**，预计要数百小时，不可行。
按工作流允许的一次参数回退改用 `check_level 1` 逐层 cosine 校验，并按官方
Qwen3-0.6B 参考配置补齐 prefill（512/128）后通过（cosine=1.0），未再触发重试。
耗时大头：权重下载约 6 分钟、llm_build2 编译约 10 分钟、embedding 处理约 9 秒、
首轮 check_level 2 约 4.5 小时（被放弃）、check_level 1 重跑约 40 分钟。

## 5. 结论与推广要点

- **单次转换的 token 费用非常低**：缓存命中率 98%+ 时，小模型全流程约 ¥0.3，
  LLM 路径约 ¥0.9。费用大头是输入上下文重发，但 DeepSeek 前缀缓存把它压到
  ¥0.02/M；
- **LLM 路径的真实瓶颈是墙钟时间而非 token 费用**：Qwen3-0.6B 无板完整跑约 5 小时，
  其中大部分是 llm_build2 校验；需要语义验证时建议直接上板，避免无板跑
  `check_level 2` 的逐位生成校验；
- 本次未上板：RUNONBOARD 与板端语义验证未执行，README 数字为“转换 + 仿真验证”
  口径，不含板端部署成本；
- token 明细可从会话 rollout 的 `total_token_usage` / `cached_input_tokens` 字段
  复算，命令与公式见 §2。

## 6. 相关文件

- 交付任务：`todos/work/yolov8n-ax650/`、`todos/work/20260812_012012-Qwen3-0.6B/`
- 会话账本：`~/.codex/sessions/2026/08/12/rollout-*.jsonl`
- 历史基准：`docs/token-efficiency.md`（早期 MobileNet 优化前后对比）
