---
name: compile
description: Hidden stage for magnetar. Compile static ONNX to AXMODEL with Pulsar2 and record compile artifacts.
---

# COMPILE

## 执行
`magnetar.stages.compile.run(task_dir, target_hw, pulsar_image)`

## 关键约束
- `highest_mix_precision` 必须为 `false`
- `calibration_std` 用 255（非 0.004）——Pulsar2 用 `/std` 公式
- 编译前确认 ONNX 为静态 shape
- 校准/输入格式先查 `docs/input-format-cheatsheet.md`（`python magnetar/pulsar2_ref.py --cases`），不要试新格式

## LLM 分支（model_route=llm）

`model_dir = magnetar.stages.llm.llm_build(task_dir, input_path=origin/<model>,
chip=TARGET_HARDWARE, pulsar_image=..., max_context=..., prefill_len=...,
weight_type=s8|s4, hidden_state_type=bf16)`

内部流程：
1. `pulsar2 llm_build2` 直接编译 HuggingFace 权重 → `compile/llm_out/`：
   逐层 `*_l%d_*.axmodel` + `*post*.axmodel` + `model.embed_tokens.weight.bfloat16.bin`，
   自带逐层 decode/prefill cosine 校验（日志 `cos_sim is: X`）；
2. `ensure_axllm_build_tools` 克隆 ax-llm-build，`embed_process.sh` 处理 embedding；
3. 组装 `compile/llm_model_dir/`：config.json（axllm 字段：tokenizer_type、
   template_filename_axmodel、axmodel_num、filename_post_axmodel、
   filename_tokens_embed、tokens_embed_num/size）+ tokenizer + axmodel +
   post_config.json + model_meta.json；
4. 生成 `export/model_meta.json`（route=llm，compile_cosine 取逐层 cosine 统计：
   min/mean/all_ge_0_99）与 `compile/compile_report.md`。

失败处理：llm_build2 报架构/head_dim/算子不支持 → 回退 EXPORT 调整参数或拆分，
仍失败 STOP 由用户决定是否回退通用 ONNX 路径；逐层 cosine < 0.99 →
回退 COMPILE 重试（weight_type s8→s4、bf16→fp16、调 max_context/prefill）。

## 验证
- `compile/model.axmodel` 存在且非空
- `compile/compile_report.md` 含 MACs、大小、压缩比、编译耗时
- LLM 分支：`compile/llm_model_dir/` 含 config.json + tokenizer + 逐层/post axmodel +
  embedding bin；`export/model_meta.json` compile_cosine.min ≥ 0.99

## STOP
- Pulsar2 编译失败且需改 ONNX → 退回 EXPORT
- 输入预处理配置与导出验证不一致
- LLM 分支：llm_build2 不可用（Pulsar2 < 6.0）→ blocked；不支持架构且用户未定回退方向
