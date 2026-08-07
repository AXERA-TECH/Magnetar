# PUBLISH（yaml step id: publish）

- kind: agent；skill: `.codex/skills/magnetar/hidden/publish/SKILL.md`
- depends_on: `package`
- inputs: package_dir / model_name
- outputs: publish_url / publish_target
- timeout: 300s；retry: 1 次（network_transient）
- on_failure: ask_user
- STOP：先问用户发布目标（GitHub 源码 / HuggingFace 预编译）、仓库名、凭据位置
- GitHub：完整源码 + model_convert；HF：仅预编译模型 + SDK；凭据 GITHUB_TOKEN / HF_TOKEN
- 后置：`publish_gate`（URL 可访问 + 无凭据泄漏）
