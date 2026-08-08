# issues/ 索引

> 查询规则：SIMULATE/COMPILE/EXPORT 失败需要参考历史时，先按"模型名 + 阶段"匹配本索引，
> 只读命中的 1-2 个文件。禁止通读全部 issue。

| 文件 | 模型 | 阶段 | 一句话结论 |
|------|------|------|------------|
| 001_F5-TTS_AxQuantizedLayerNorm_compile_blocked.md | F5-TTS | COMPILE | AxQuantizedLayerNorm 算子编译阻塞 |
| 006_yolov8_ax-pipeline_integration_guide.md | YOLO 类 | 集成 | ax-pipeline 集成指南，YOLO 交付必读 |
| 007_bosonai_higgs_tts_ax650_feasibility.md | BosonAI Higgs TTS 3 4B | 可行性 | AX650 可转性分析 |
| 008_chatterbox_ve_lstm_compile_blocked.md | Chatterbox VE | COMPILE | LSTM 结构 Pulsar2 编译失败 |
| 009_audio8-tts_codec_snake_compile.md | Audio8-TTS 0.6b | COMPILE | codec Snake 编译问题 |
| 010_audio8-tts_slow_ar_npu_precision.md | Audio8-TTS 0.6b | SIMULATE | Slow AR NPU 精度/编译问题 |
| 011_xtts-v2_npu_compile_blocked.md | XTTS-v2 | COMPILE | 风格前端子图 NPU 编译阻塞 |
| 012_neutts2e_llmbuild_head_dim_rtf.md | NeuTTS-2E | COMPILE/RUN | llm_build head_dim 断言 + host-KV RTF 上限 |
| 013_moss-tts-realtime_ax650_pipeline_pitfalls.md | MOSS-TTS-Realtime | 全流程 | 部署全流程踩坑记录 |
| diarizen_pipeline_issues.md | DiariZen | EXPORT | opset17 LayerNormalization 导出失败 |
| kokoro_pipeline_issues.md | kokoro | COMPILE | Pulsar2/PPQ 不支持 SequenceEmpty |
| melotts_pipeline_issues.md | MeloTTS | COMPILE | AX650 backend AxClip S32 failure |
| piper_tts_experience.md | PiperTTS | 经验 | 中文 TTS 转换经验总结 |
| yolo_quantization_and_compile.md | YOLO | 量化 | Per-Tensor 量化小值通道压 0 的根因与方案 |

## 常见匹配建议

- TTS 类模型 COMPILE 失败 → 先看 001/008/009/010/011/012
- 自回归/类 LLM 模型（Qwen/Llama/MiniCPM/GPT、含 LLM 骨干的 TTS）→ 先走 ax-llm
  路由（`magnetar.stages.llm.classify` → `pulsar2 llm_build2` → axllm），
  COMPILE 失败参考 012（llm_build head_dim 断言）与 013（MOSS-TTS 全流程）
- 检测类模型（YOLO）→ 006 + yolo_quantization_and_compile
- EXPORT 阶段 LayerNorm/opset 失败 → diarizen_pipeline_issues
- 校准数据 / pulsar2 run / ax_run_model 输入格式问题 → 先看 `docs/input-format-cheatsheet.md`（成功案例固化），再看 piper/013/yolo 量化记录
- 精度不达标且 INT8/U16/混合精度全失败 → 向用户提议上 QAT（官方 `AXERA-TECH/QAT.axera`），先看 piper_tts_experience §2（QAT→QDQ）与 melotts_pipeline_issues（QAT.axera 记录）
- 新增 issue 时更新本索引
