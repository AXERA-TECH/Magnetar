# 013 MOSS-TTS-Realtime AX650 部署全流程踩坑记录

日期：2026-08-05
状态：暂停（骨干量化精度不达标）

## 任务

将 `OpenMOSS-Team/MOSS-TTS-Realtime`（1.7B：Qwen3 28L×2048 骨干 + 4L×2048 local transformer，16 路 RVQ 音频 token）配合 `OpenMOSS-Team/MOSS-Audio-Tokenizer`（24kHz 单声道，16 量化器）转换为 AX650/NPU3 AXMODEL，优先中文。Pulsar2 使用本机 `ax_pulsar2_7.0_lite.tar.gz`（docker 镜像 `pulsar2:7.0-lite`）。

## 已产出（ONNX + AXMODEL）

- `tts_prefill_p0/p1/p2.axmodel`（按 10/9/9 层拆分，各 <2GB）
- `tts_decode_step_p0/p1/p2.axmodel`
- `tts_local_step.axmodel`（单步 local transformer，host 端采样）
- `codec_encoder.axmodel`、`codec_decode.axmodel`
- Python 板端推理（axengine）已能跑通 prefill + 帧生成 + codec 解码

## 关键踩坑

### 1. 环境
- 模型代码需要 **transformers 5.0.0**（4.57.1 缺 `transformers.initialization`）。并行任务可能把 venv 降级，使用前必须复查版本。
- 网络：hf-mirror/huggingface.co 仅 ~1MB/s，4.7GB 权重用 **ModelScope CDN 分片并行下载**（`cdn-lfs-cn-1.modelscope.cn` 支持 Range，32 线程 ~1.5MB/s）。tokenizer.json 等小文件走 hf-mirror 单线即可。
- 本机 `/data/shared/huyuan/` 已有 MOSS-TTS-Nano 全套 AXERA 工程（导出/量化/板端 C++），是重要参考。

### 2. ONNX 导出
- Qwen3 注意 GQA：KV 头 8 → 16 需 `repeat_kv`；KV cache 输入按 `[K0..K27, V0..V27]` 顺序（交错会得到错乱结果）。
- torch 导出大模型会产生大量 Constant/ConstantOfShape → Pulsar2 强制 onnxsim 且 >2GB 时报 `narrowing_error`。解法：先用本机 onnxsim 简化（保留外部权重单文件 `.data`），并把 `onnx_opt.disable_onnx_optimization=true`。
- 数值验证：prefill/decode hidden cos≈1.0、local logits cos≈1.0 后再进入编译。

### 3. Pulsar2 编译
- **授权**：Sentinel v2c 必须挂载到容器内 `/root/.hasplm`（`-v /tmp/p2_verify_home/.hasplm:/root/.hasplm -e HASP_HOME=/root/.hasplm` 并在启动时 `cp /root/*.v2c` 到 `installed/32434/`）。挂 `/tmp/...` 路径报 `Sentinel key not found (H0007)`。
- **2GB protobuf 上限**：量化模型 external data >2GB 时 GraphFusion 报 `DecodeError("Error parsing message with type 'onnx.TensorProto')`。解法：把 28 层骨干按层拆成多个子模型（本任务用 10/9/9），每个量化产物 <2GB；运行时按序串联。
- **不要 16 次展开 local transformer 成一张图**（GraphFusion 同错）；改用单步 `local_step`（输入 global_hidden/prev_token/channel_index/past_valid_lengths + 4 层静态 16 槽 KV），host 端做 top-k/top-p 采样，帧内调用 16 次。
- `codec_decode_step`（流式层级 codec）有 278 个输入 → NPU 后端 IO 数超限，无法编译；用 `codec_decode` 全量（128 帧）替代。
- 拆分模型输入名会被 torch 改写成 `hidden.1`，需把 graph.input 与所有 node 引用统一改回 `hidden`、输出改名 `hidden_out`（只改 graph.output 会导致“未连接到任何算子”）。
- Pulsar2 校准 tar.gz 内是 `{input_name}/{index:05d}.npy`，样本需带 batch 维（如 [1,512,17]），且 `tensor_name` 必须与 ONNX 输入名一致（校准文件名可不同）。
- 每次编译前清掉 `build-*/work-*`（root 属主用 pulsar2 容器 chown 后再删），避免旧图缓存导致 Shape/旧配置残留。

### 4. 板端（AX650N，10.126.35.143）
- 板子 3.4GB 内存，**9 个 axmodel 不能同时加载**（会 Failed to load model）；按阶段懒加载：codec_encoder →（释放）→ prefill 三部 →（释放）→ decode 三部 + local_step →（释放）→ codec_decode。
- axengine 0.1.3 API：`run(output_names, input_feed)`、`get_inputs()/get_outputs()`（无 `get_io_info`），输入 dtype 从 `NodeArg.dtype` 读取并强制转换。
- 板端 local_step 用 host 的 global_hidden 输出与 ONNX 完全一致（top-5 logits 相同）→ local 量化无问题。
- **未解决问题**：板端 prefill hidden 与 host ONNX cos 仅 0.37（p0=0.84→p1=0.79→p2=0.37），导致 local 采样直接出 EOS/乱码。尝试过：U16+MinMax 全层、embedding/首层 RMSNorm 改 FP32+关 SmoothQuant（更差，cos 0.26）、KL+16 样本（编译未完成即暂停）。**U16 量化该 28L 骨干质量不达标，需要进一步调优**（更大校准集、逐层精度分析、混合精度或权重 FP16/更激进策略）。

## 建议后续方向

- 用 `precision_analysis=true` 找出退化层，做分层混合精度（U16/U8/FP32 组合）。
- 增大校准集（>32 条中英文本 + 更多真实音色 prompt），尝试 Percentile/MSE 标定。
- 考虑骨干 FP16 或 SplitK 等 Pulsar2 增强（`highest_mix_precision` 相关）重新评估。
