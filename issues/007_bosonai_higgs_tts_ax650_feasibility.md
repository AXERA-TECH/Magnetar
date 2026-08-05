# BosonAI Higgs TTS 3 4B AX650 可转性分析

## 结论

`bosonai/higgs-tts-3-4b` 不适合走标准 Qwen3 文本 LLM 的一键转换路线。

它的 text backbone 是 Qwen3-4B，理论上可参考 `AXERA-TECH/Qwen3-4B` 用 Pulsar2 `llm_build` 转到 AX650；但完整模型是 `HiggsMultimodalQwen3ForConditionalGeneration`，包含 8-codebook audio token/head、delay pattern、acoustic decoder/quantizer/code2wav 逻辑。现有 `ax-llm` runner 没有 Higgs TTS `/v1/audio/speech` 输出链路。

## 证据

- HF config:
  - `model_type = higgs_multimodal_qwen3`
  - `architectures = HiggsMultimodalQwen3ForConditionalGeneration`
  - `text_config.model_type = qwen3`
  - Qwen3: 36 layers, hidden 2560, 32 heads, 8 kv heads
  - audio encoder: 8 codebooks, vocab 1026, delay pattern
- HF weight map:
  - `body.*`: Qwen3-like transformer backbone
  - `tied.embedding.modality_embeddings.0.*`: acoustic decoder, quantizer, codec/codebook related modules
- vLLM-Omni Higgs v3 pipeline:
  - Stage 0: Talker, text -> 8-codebook codec latent
  - Stage 1: Code2Wav, codec -> 24 kHz PCM
- AXERA reference:
  - `AXERA-TECH/Qwen3-4B`: text Qwen3-4B on AX650, w8a16, 36 layer axmodels + post + bf16 embedding
  - `AXERA-TECH/Qwen3-TTS-12Hz-0.6B-Base-AX650`: TTS package uses `talker/`, `code-predictor/`, `speech_tokenizer/`, and Python `infer.py`

## 建议路线

1. 不导出完整 Higgs 单体 ONNX。
2. 抽取/适配 Qwen3 backbone 到 Pulsar2 LLM build 输入。
3. 将 Higgs fused multi-codebook embedding/head 拆为可验证的 CPU/Python glue 或单独 AXMODEL。
4. 参照 vLLM-Omni 的 Talker -> Code2Wav 和 AXERA Qwen3-TTS `infer.py`，做多 AXMODEL Python SDK。
5. 每个子图先做 HF/PyTorch vs NPU 对分，再进行 waveform 端到端验证。

## STOP

继续前需要确认是否接受自定义拆分路线，以及是否允许下载 9GB 权重和拉取/复用 vLLM-Omni 或 SGLang-Omni 的 Higgs 实现作为参考。
