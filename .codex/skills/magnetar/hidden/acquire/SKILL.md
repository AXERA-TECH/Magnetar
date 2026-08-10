---
name: acquire
description: Hidden stage for magnetar. Acquire a remote or local model into TASK_DIR/origin without modifying the source.
---

# ACQUIRE

## 执行
`magnetar.stages.acquire.run(task_dir, source)`

下载镜像默认：ModelScope 优先（国内 CDN）；HuggingFace 走 `HF_ENDPOINT`（默认 hf-mirror）；
Git URL 克隆经 `GH_PROXY`（默认 gh-proxy）；uv/pip 用 `PIP_INDEX_URL`（默认阿里云）。
全部可在 `.magnetarrc` / 环境变量覆盖，置空字符串禁用。
SOURCE 为 HF repo 时，先 `magnetar.net_util.modelscope_available("<org>/<name>")`
探测 ModelScope 是否有同名仓库，有则 `modelscope download --model <org>/<name>` 获取，
没有才回退 HuggingFace（hf-mirror）。
HF 大文件（权重/大附件）回退时用 hf-mirror 的 hfd 工具多线程下载：
`scripts/download_hf.sh <org>/<name> --local-dir origin/<name> -x 8`
（自动缓存 `~/.cache/magnetar/hfd.sh`，`HF_ENDPOINT` 默认 hf-mirror；小文件
如 tokenizer.json 可直接 `curl/wget $HF_ENDPOINT/...` 单线获取）。

拿到模型后，**记录运行流程**：调用 `magnetar.stages.acquire.write_model_flow(task_dir, flow)`
写入 `origin/model_flow.json`，字段见函数 docstring。至少包含：
- `example_input`：真实样本路径（保证 SDK 用与验证一致的数据）
- `preprocess_code` / `postprocess_code`：预处理/后处理函数体（SDK 原样嵌入）
- `verified: true`：表示该流程已实际跑通模型

SDK-GEN 阶段必须读取此文件生成 SDK，确保与 ACQUIRE 验证过的运行流程一致；
缺失或示例样本不存在时 SDK 生成会报错。

## LLM/自回归检测（model_route gate 的输入）

拿到模型后用 `magnetar.stages.llm.classify(origin, source, model_name)` 判定并把结果
写入 `cache/acquire/manifest.json` 的 `route_hint`：
- `{"llm": true|false, "reason": "...", "hybrid": true|false}`

检测信号（命中任一即 route=llm）：
- `config.json` 的 `architectures`/`model_type`（含嵌套 `text_config`）为 causal LM，
  如 `Qwen2ForCausalLM`、`LlamaForCausalLM`、`MiniCPMForCausalLM`
- README.md 的 `pipeline_tag: text-generation`
- `model_flow.json` 的 task 为 text_generation / causal_lm / chat
- SOURCE/MODEL_NAME 含已知 LLM 名称；MOSS、NeuTTS、VALL-E、Audio8 等为 hybrid
  （整体 TTS 但含 LLM/AR 骨干，需拆分，`hybrid: true`）

## 验证
- `origin/` 下有模型文件或 `source.txt`
- `ACQUIRE_REPORT.md` 已生成
- `model_flow.json` 已记录运行流程（缺失时 SDK-GEN 只能生成直通预处理/后处理，需 Agent 注意）
- `route_hint` 已写入 manifest.json（供 model_route gate 复用）

## STOP
- SOURCE 无效（本地路径不存在、URL 不可达、Git clone 失败）
- 需要私有凭据（HF_TOKEN 缺失）
