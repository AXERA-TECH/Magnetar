# INIT（yaml step id: init）

- kind: agent；skill: `.codex/skills/magnetar/hidden/init/SKILL.md`
- depends_on: `stage_review_acquire`
- inputs: TASK_DIR / MODEL_NAME / TARGET_HARDWARE / acquire_manifest / uv
- outputs: task_md / analysis_md
- timeout: 120s；retry: 1 次（filesystem_transient）
- on_failure: fail
- 要点：建 TASK_DIR 九个子目录 + task.md/analysis.md/config.json；任务参数固化到 config.json，
  后续阶段读 `magnetar.config.load_task_config(task_dir)`，不反复改 `.magnetarrc`
- 环境：不重复建大环境——共享 base venv（`python -m magnetar.env_util base`，大包只装一次）；
  任务薄 venv 用 `magnetar.env_util.create_task_venv(task_dir, extra_packages=...)` 创建，
  VENV_PATH 固化进 config.json；解释器统一 `resolve_task_python(task_dir)`
- 后置：`dry_run_check`
