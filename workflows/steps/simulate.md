# SIMULATE（yaml step id: simulate）

- kind: agent；skill: `.codex/skills/magnetar/hidden/simulate/SKILL.md`
- depends_on: `stage_review_compile`
- inputs: onnx_path / axmodel_path / axmodel_dir / model_meta_json / TASK_DIR / BOARD / BOARD_PASSWORD / TARGET_HARDWARE / model_route
- outputs: simulate_report / accuracy_metrics / simulation_latency_ms
- timeout: 1200s；retry: 1 次（simulation_transient / tool_error）
- on_failure: rollback → COMPILE（调整量化配置）
- 要点：有板必上板（ax_run_model 秒级，先 `ensure_remote_infer`），无板才 pulsar2 run；
  输入/输出格式用 `magnetar/io_format.py`；精度不达标先查 `issues/`
- 板端并发安全：上板前自动申请独占租约（`board_util.acquire_board_lease`，原子
  mkdir 抢锁，mtime 心跳 30 分钟）；板子被占用时 SIMULATE 自动回退 pulsar2 run，
  所有临时文件只在 `/tmp/magnetar-lease/<token>/` 命名空间下，绝不清理他人环境
- LLM 分支：有板 → 装 axllm（`magnetar.stages.llm.install_axllm`）+ `axllm serve
  compile/llm_model_dir`，OpenAI 兼容接口 ≥3 组 prompt greedy 语义验证
  （`validate_chat`，记录响应非空/token 数/耗时）；serve 目录在板端租约命名空间
  （/tmp/magnetar-lease/<token>/serve），验证完用 `stop_serve(board, rd)` 按 PID
  精确停止（rd 为 serve_axllm 返回值，禁止 pkill 全板）；无板 → 回退
  `llm_build2 --check_level 2 --prompt ...` 逐层 cosine 校验（`_extract_cosims`），
  语义验证留给 RUNONBOARD
- 后置：`accuracy_gate`（general cosine ≥ 0.99；llm 逐层 cosine min ≥ 0.99；
  全失败 → 先调 weight_type/context，再提议 QAT，官方 QAT.axera）
