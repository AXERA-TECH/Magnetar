# Token 效率基准：一次完整模型转换的实测账本

> 样本：MobileNetV3-Small（torchvision 预训练）→ AX650，Pulsar2 7.0-lite，INT8。
> 流程：EXPORT → COMPILE → SIMULATE（pulsar2 run 回退）。
> 日期：2026-08-07。

## 实测数据

| 阶段 | 耗时 | 关键产物 |
|------|------|----------|
| EXPORT | ~5s | model.onnx 10.2MB、calib_data/input.tar.gz 3.4MB、Torch/ONNX cosine=1.0 |
| COMPILE | 51s | model.axmodel 3.2MB、compile.log 44.9KB（566 行） |
| SIMULATE | 43s | pulsar2_run.log 462B、cosine=0.60（随机校准样本，见下） |

本次会话 goal 计量：**32,850 tokens / 306s**（含一次 license 失败重试，重试部分已随下述优化消除）。

## 优化前后 token 对比

### 1. 日志/异常截断（大头，实测）

| 场景 | 优化前 | 优化后 | 省 |
|------|--------|--------|-----|
| COMPILE 失败 | 异常带全量 compile.log（44,858 chars ≈ 11–22k tokens） | 异常 ≤4,000 chars（≈ 1–2k tokens）+ 日志路径 | ~10–20k tokens/次失败 |
| 本次实际踩到的失败 dump | ~14k tokens（license 失败那次） | 同场景 ≈1k tokens | ~13k tokens |

教训：**纯按行数截断不够**——compile.log 尾部是精度分析大表，400 行仍有 32k chars。
现已改为“行数 400 + 字符 4000”双上限（`magnetar/docker_util.py::run`），完整日志只落盘。

### 2. 工作流文档按需读取（workflows 拆分）

| 读取对象 | 字符 | token 估算（÷4~÷2） |
|----------|------|---------------------|
| `workflows/magnetar.yaml` 全文 | 30,026 | 7.5k–15k |
| `workflows/magnetar-summary.md`（全局一次） | 2,706 | 0.7k–1.4k |
| `workflows/steps/` 10 个片段（每阶段一个） | ~7.6k 合计 | 1.9k–3.8k |
| 每阶段重读 yaml（10 次）× 转换 | 300k | 75k–150k |
| 每阶段读片段 + 全局摘要一次 | ~10.3k | 2.6k–5.1k |

按“每阶段重读一次状态机”的旧习惯，拆分后每转换省 ~290k chars（≈ 7.3万–14.5万 tokens）；
即使只读一次，也省 ~21k chars（≈ 5k–10k tokens）。

### 3. 校准数据质量对精度的直接影响（顺带验证）

本次用 8 个随机扰动样本做 INT8 校准 → SIMULATE cosine=**0.60**（<0.99）。
印证“随机数据也许有用，真实业务上可能出错”：随机校准连 ImageNet 分类这种常规任务都过不了阈值，
真实业务数据校准是精度达标的前提（见 `docs/input-format-cheatsheet.md` §1）。

## 单次转换预估 token 账本（优化后）

- 文档读取：~3–5k tokens
- 各阶段输出（EXPORT/COMPILE/SIMULATE）：~1–3k tokens（日志截断 + 落盘）
- 失败重试：单次失败 ≤1–2k tokens（旧流程单次失败即 10–20k）
- 合计预估：**5–10k tokens/转换**（顺利路径），对比优化前至少省 2 万–15 万 tokens

## 附：本次顺带修复

- `docker_pulsar2` 启动时把镜像内 `/root/*.v2c` 装入 `/root/.hasplm/installed/32434/`，
  修复 Sentinel `H0007` license 失败（见 `issues/013`）。
