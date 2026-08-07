# TOOLCHAIN（yaml step id: toolchain）

- kind: agent；skill: `.codex/skills/magnetar/hidden/toolchain/SKILL.md`
- depends_on: `stage_review_export`
- inputs: PULSAR2_IMAGE / PULSAR2_BIN / PULSAR2_HF_REPO / TASK_DIR / TARGET_HARDWARE / CXX_BSP_URL / HF_ENDPOINT
- outputs: pulsar2_command / cxx_toolchain_file / ax_runtime_root
- timeout: 1200s；retry: 1 次（download_failed / docker_pull_failed）
- on_failure: ask_user（Pulsar2 / BSP 不可获取）
- 要点：验证 Pulsar2 可用 + 准备芯片 C++ BSP/交叉编译器；Pulsar2 镜像走 hf-mirror
- 后置：`pulsar2_available` gate → COMPILE
