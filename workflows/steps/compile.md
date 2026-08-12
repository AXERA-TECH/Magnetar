# COMPILE（yaml step id: compile）

- kind: agent；skill: `.codex/skills/magnetar/hidden/compile/SKILL.md`
- depends_on: `toolchain`
- inputs: onnx_path / model_meta_json / calibration_dir / TARGET_HARDWARE / pulsar2_command / model_route
- outputs: axmodel_path（general）/ axmodel_dir（llm）/ compile_report
- timeout: 3600s；retry: 1 次（compile_failed / pulsar2_transient）
- on_failure: rollback → EXPORT（调 ONNX 导出策略；llm 路由调 llm_build2 参数或拆分）
- 要点：ONNX 必须静态 shape；`highest_mix_precision=false`；U8 校准 `calibration_std=255`；
  日志只取摘要（`summarize_compile_log`）
- 预检（v3）：编译前自动跑三重校验，全过才启动编译（独立包/镜像通用）——
  1) proto schema 字段级校验（`magnetar/proto_schema.py`，未知字段/类型/枚举/必填）；
  2) model_meta 交叉校验 + 校准集内容预检（`magnetar/io_format.py::validate_calibration_archive`）；
  3) config-check 权威兜底（Pulsar2 自身 build_config_pb2 解析，`docker_pulsar2_config_check`）。
  预检失败即停止，报错自带修复提示，不需要再翻文档；仅排障用 `MAGNETAR_SKIP_PREFLIGHT=1` 跳过。
- LLM 分支：`pulsar2 llm_build2 --input_path origin/... --chip <chip> --max_context ...
  --prefill_len ... --weight_type s8|s4 --hidden_state_type bf16`（Pulsar2 ≥ 6.0，
  需先 `pulsar2 llm_build2 -h` 确认）；产物逐层 `*_l%d_*.axmodel` + `*post*.axmodel` +
  `model.embed_tokens.weight.bfloat16.bin`；用 ax-llm-build `embed_process.sh` 处理
  embedding，组装 `compile/llm_model_dir/`（config.json + tokenizer + axmodel +
  post_config.json + model_meta.json）；compile_report 记录逐层 cosine（自带校验）
- 后置：`stage_review_compile`
