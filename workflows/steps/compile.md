# COMPILE（yaml step id: compile）

- kind: agent；skill: `.codex/skills/magnetar/hidden/compile/SKILL.md`
- depends_on: `toolchain`
- inputs: onnx_path / model_meta_json / calibration_dir / TARGET_HARDWARE / pulsar2_command
- outputs: axmodel_path / compile_report
- timeout: 3600s；retry: 1 次（compile_failed / pulsar2_transient）
- on_failure: rollback → EXPORT（调 ONNX 导出策略）
- 要点：ONNX 必须静态 shape；`highest_mix_precision=false`；U8 校准 `calibration_std=255`；
  配置/格式问题先查 `docs/input-format-cheatsheet.md`；日志只取摘要（`summarize_compile_log`）
- 后置：`stage_review_compile`
