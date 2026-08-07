# RUNONBOARD（yaml step id: runonboard）

- kind: agent；skill: `.codex/skills/magnetar/hidden/runonboard/SKILL.md`
- depends_on: `sdk_gen`
- inputs: TASK_DIR / BOARD / BOARD_PASSWORD / TARGET_HARDWARE
- outputs: runonboard_report
- skip_condition: BOARD 未提供（缺失不是 STOP）
- 要点：选板后先 `ensure_remote_infer(board)`（18500 未装自动静默安装）；
  Python/C++ SDK 板端运行，cosine ≥ 0.98 + 延迟/内存
- 后置：`stage_review_runonboard`（AUTO_APPROVE=true 或无 BOARD 时跳过）→ PACKAGE
