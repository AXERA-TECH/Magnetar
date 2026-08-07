# EXPORT（yaml step id: export）

- kind: agent；skill: `.codex/skills/magnetar/hidden/export/SKILL.md`
- depends_on: `dry_run_check`
- inputs: origin_path / acquire_manifest / TASK_DIR / HF_ENDPOINT / uv
- outputs: onnx_path / model_meta_json / calibration_dir / export_report
- timeout: 3600s；retry: 1 次（export_failed / validation_mismatch / compile_rollback）
- on_failure: ask_user（多次失败需用户介入）
- 要点：静态 ONNX + Torch/ONNX cosine ≥ 0.99；校准集尽量用真实业务数据
  （`calibration_data=` / `--calib-dir`），扰动仅兜底；格式见 `docs/input-format-cheatsheet.md`
- 后置：`stage_review_export` + `export_valid` gate
