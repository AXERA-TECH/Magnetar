# EXPORT（yaml step id: export）

- kind: agent；skill: `.codex/skills/magnetar/hidden/export/SKILL.md`
- depends_on: `model_route`
- inputs: origin_path / acquire_manifest / TASK_DIR / HF_ENDPOINT / PIP_INDEX_URL / uv / model_route
- outputs: onnx_path（general）/ model_meta_json / calibration_dir / export_report
- timeout: 3600s；retry: 1 次（export_failed / validation_mismatch / compile_rollback）
- on_failure: ask_user（多次失败需用户介入）
- 要点：静态 ONNX + Torch/ONNX cosine ≥ 0.99；校准集尽量用真实业务数据
  （`calibration_data=` / `--calib-dir`），扰动仅兜底；格式见 `docs/input-format-cheatsheet.md`
- 环境：先 `ensure_base_env()`（大包共享），再 `create_task_venv(task_dir,
  extra_packages=<模型特有依赖>)` 建薄 venv；禁止重建完整 torch/transformers 环境
- LLM 分支（model_route=llm）：不导出 ONNX。验证 HuggingFace 权重可推理（跑通一次
  source 生成并保存参考输出），生成可复现 `export/llm_build.sh`（完整 llm_build2 命令），
  记录 tokenizer/模型参数到 model_meta；hybrid 模型同时用通用路径导出非 LLM 子模型
- 后置：`stage_review_export` + `export_valid` gate
