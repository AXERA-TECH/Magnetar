# COMPILE（yaml step id: compile）

- kind: agent；skill: `.codex/skills/magnetar/hidden/compile/SKILL.md`
- depends_on: `toolchain`
- inputs: onnx_path / model_meta_json / calibration_dir / TARGET_HARDWARE / pulsar2_command / model_route
- outputs: axmodel_path（general）/ axmodel_dir（llm）/ compile_report
- timeout: 3600s；retry: 1 次（compile_failed / pulsar2_transient）
- on_failure: rollback → EXPORT（调 ONNX 导出策略；llm 路由调 llm_build2 参数或拆分）
- 要点：ONNX 必须静态 shape；`highest_mix_precision=false`；U8 校准 `calibration_std=255`；
  配置/格式问题先查 `docs/input-format-cheatsheet.md`；日志只取摘要（`summarize_compile_log`）
- LLM 分支：`pulsar2 llm_build2 --input_path origin/... --chip <chip> --max_context ...
  --prefill_len ... --weight_type s8|s4 --hidden_state_type bf16`（Pulsar2 ≥ 6.0，
  需先 `pulsar2 llm_build2 -h` 确认）；产物逐层 `*_l%d_*.axmodel` + `*post*.axmodel` +
  `model.embed_tokens.weight.bfloat16.bin`；用 ax-llm-build `embed_process.sh` 处理
  embedding，组装 `compile/llm_model_dir/`（config.json + tokenizer + axmodel +
  post_config.json + model_meta.json）；compile_report 记录逐层 cosine（自带校验）
- 后置：`stage_review_compile`
