# RUNONBOARD（yaml step id: runonboard）

- kind: agent；skill: `.codex/skills/magnetar/hidden/runonboard/SKILL.md`
- depends_on: `sdk_gen`
- inputs: TASK_DIR / BOARD / BOARD_PASSWORD / TARGET_HARDWARE / GH_PROXY / model_route
- outputs: runonboard_report / llm_metrics（TTFT / token 速率 / 内存）
- skip_condition: BOARD 未提供（缺失不是 STOP）
- 要点：选板后先 `ensure_remote_infer(board)`（18500 未装自动静默安装）；
  Python/C++ SDK 板端运行，cosine ≥ 0.98 + 延迟/内存
- 板端并发安全：上板前申请独占租约（`board_util.acquire_board_lease`）；板子被
  占用时本阶段跳过（mark skipped，不阻塞交付），临时文件只在自己 token 目录下
- LLM 分支：`install_axllm(board)`（ax-llm install.sh，编译耗时较长）；
  `serve_axllm(board, compile/llm_model_dir, port)` 启动 OpenAI 兼容服务（目录在
  租约命名空间下）；板端运行 Python SDK 示例（`validate_chat` 语义验证 ≥3 组
  prompt），记录 TTFT（serve 日志）/ 生成 token 数 / token 速率 / 系统内存增量 /
  CMM 占用；验证完 `stop_serve(board, rd)` 按 PID 停止并释放租约（rd 为返回值）
- 后置：`stage_review_runonboard`（AUTO_APPROVE=true 或无 BOARD 时跳过）→ PACKAGE
