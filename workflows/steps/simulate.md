# SIMULATE（yaml step id: simulate）

- kind: agent；skill: `.codex/skills/magnetar/hidden/simulate/SKILL.md`
- depends_on: `stage_review_compile`
- inputs: onnx_path / axmodel_path / model_meta_json / TASK_DIR / BOARD / BOARD_PASSWORD / TARGET_HARDWARE
- outputs: simulate_report / accuracy_metrics / simulation_latency_ms
- timeout: 1200s；retry: 1 次（simulation_transient / tool_error）
- on_failure: rollback → COMPILE（调整量化配置）
- 要点：有板必上板（ax_run_model 秒级，先 `ensure_remote_infer`），无板才 pulsar2 run；
  输入/输出格式用 `magnetar/io_format.py`；精度不达标先查 `issues/`
- 后置：`accuracy_gate`（cosine ≥ 0.99；INT8/U16/混合精度全失败 → 提议 QAT，官方 QAT.axera）
