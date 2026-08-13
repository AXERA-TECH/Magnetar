# 爱芯开发知识（AXera Knowledge）

> 本文件是 AGENTS.md 中"爱芯开发知识"的完整内容，仅在需要查证具体 URL/版本时按需读取，
> 不随每个 turn 全量加载。

## 常用资源

- 先查 ModelScope（国内 CDN 快）：涉及 HF 的内容先看
  https://modelscope.cn/models/AXERA-TECH 有没有，无才回退 hf-mirror
- HF 大文件下载（hfd，hf-mirror 多线程工具）:
  `wget https://hf-mirror.com/hfd/hfd.sh`，封装脚本 `scripts/download_hf.sh`
  （缓存 `~/.cache/magnetar/hfd.sh`，`HF_ENDPOINT` 默认 hf-mirror，aria2c 优先）
- Pulsar2 镜像 (ModelScope): https://modelscope.cn/models/AXERA-TECH/Pulsar2
- Pulsar2 镜像: https://hf-mirror.com/AXERA-TECH/Pulsar2
- Pulsar2 文档: https://pulsar2-docs.readthedocs.io/zh-cn/latest/
- 爱芯 HF: https://hf-mirror.com/AXERA-TECH
- 爱芯 GitHub: https://github.com/AXERA-TECH
- 交叉编译器: https://github.com/AXERA-TECH/ax-samples/tree/main/docs
- 获取BSP: https://github.com/AXERA-TECH/ax-pipeline/blob/main/scripts/build_common.sh
  （BSP/runtime 与交叉编译器的下载地址按芯片 case 解析：`MSP_URL_DEFAULT` /
  `TOOLCHAIN_URL_DEFAULT`）
- 芯片命名：AX620E 是 NPU 芯片名称，对应 SoC 有 AX630C、AX620Q；这些 SoC 的
  BSP 和交叉编译器都收录在 build_common.sh 里（ax630c / ax620q 两个 case）
- LLM 编译: https://github.com/AXERA-TECH/ax-llm
- ax-llm 分支: https://github.com/AXERA-TECH/ax-llm/tree/axllm（统一可执行文件名 axllm，
  AX650 片上 / AXCL PCIe 双后端）
- ax-llm 安装: `curl -fsSL https://raw.githubusercontent.com/AXERA-TECH/ax-llm/axllm/install.sh | bash`
- ax-llm-build（LLM 编译辅助，embedding 处理）: https://github.com/AXERA-TECH/ax-llm-build
- Pulsar2 LLM 编译文档: https://pulsar2-docs.readthedocs.io/en/latest/appendix/build_llm.html
- axllm 配置字段: https://github.com/AXERA-TECH/ax-llm/blob/axllm/docs/configuration.md

## LLM/自回归模型（ax-llm 路径）

- 触发：`magnetar.stages.llm.classify` 判定 route=llm（causal LM / chat / 含 LLM 骨干
  的 TTS 如 MOSS-TTS、NeuTTS-2E）；hybrid 需确认 LLM/AR 子模型拆分。
- 编译：`pulsar2 llm_build2 --input_path <HF权重目录> --output_path <out>
  --chip AX650 --max_context 1024 --prefill_len ... --weight_type s8|s4
  --hidden_state_type bf16 --parallel 8`（Pulsar2 ≥ 6.0，需
  `FLOAT_MATMUL_USE_CONV_EU=1`）；自带逐层 decode/prefill cosine 校验。
- 板端运行：`axllm run <model_dir>` / `axllm serve <model_dir> --port 8000`
  （OpenAI 兼容 `/v1/chat/completions`）；模型目录含 config.json + tokenizer +
  逐层/post axmodel + embedding bin。
- 支持芯片：AX650A/AX650N（SDK ≥ 3.6.2）、AX630C（SDK ≥ 3.0.0）；gemma-4 仅片上
  AX650 后端可正常推理（AXCL 后端有 shared-KV 数值发散，见 ax-llm README 已知限制）。
- 验证：LLM 路由不适用张量级 cosine 对分，用逐层 cosine（compile 自带）+ 板端
  OpenAI 兼容接口语义验证（≥3 组 prompt，greedy，全非空），指标记 TTFT/token 速率/内存。

## 输入格式速查

- 校准数据 / pulsar2 run / ax_run_model / axengine 输入格式的成功案例固化：`docs/input-format-cheatsheet.md`
- 代码层单一来源：`magnetar/io_format.py`；`python magnetar/pulsar2_ref.py --cases` 打印成功案例

## QAT（量化感知训练）

INT8 / U16 / 混合精度（layer_configs、SmoothQuant、Brecq、Percentile 等）全部尝试
仍 cosine < 0.99 时，SIMULATE 到达 STOP 点，先向用户提议上 QAT。QAT 需要训练数据
和训练时间，成本高，必须用户确认后才进入。

- 框架必须使用官方 `AXERA-TECH/QAT.axera`，不得改用其他 QAT 实现
  （保证与 Pulsar2 编译链路兼容）
- 优先 QAT→QDQ ONNX 通道：Pulsar2 的 PTQ 会重新计算 scale，把 QAT 训练收益归零
  （见 `issues/piper_tts_experience.md` §2）
- QAT.axera 基础 fake-quant 链路可用，但训练稳定性需先做 toy sanity
  （见 `issues/melotts_pipeline_issues.md` QAT 追加记录）
- 用户确认后进入 QAT，通常退回 EXPORT 重新导出 QDQ ONNX

## 本机环境

- 本机 Docker 可能已安装 Pulsar2，优先使用最新版本
- 调试问题记录到 `issues/`，命名 `序号_模型名_阶段_问题简述.md`；查询前先读 `issues/INDEX.md`
