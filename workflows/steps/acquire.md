# ACQUIRE（yaml step id: acquire）

- kind: agent；skill: `.codex/skills/magnetar/hidden/acquire/SKILL.md`
- depends_on: `requirements_gate`
- inputs: SOURCE / HF_TOKEN / TASK_DIR / HF_ENDPOINT
- outputs: origin_path / acquire_manifest
- timeout: 900s；retry: 1 次（network_timeout / partial_download，指数退避）
- on_failure: ask_user（SOURCE 无效 / 私有凭据缺失）
- 要点：模型获取优先 ModelScope，HuggingFace 仅回退；拿到模型后写 `origin/model_flow.json`
- 后置：`stage_review_acquire`（AUTO_APPROVE=true 时跳过）
