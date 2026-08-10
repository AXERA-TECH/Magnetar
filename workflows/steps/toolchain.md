# TOOLCHAIN（yaml step id: toolchain）

- kind: agent；skill: `.codex/skills/magnetar/hidden/toolchain/SKILL.md`
- depends_on: `stage_review_export`
- inputs: PULSAR2_IMAGE / PULSAR2_BIN / PULSAR2_HF_REPO / TASK_DIR / TARGET_HARDWARE / CXX_BSP_URL / HF_ENDPOINT / GH_PROXY
- outputs: pulsar2_command / cxx_toolchain_file / ax_runtime_root
- timeout: 1200s；retry: 1 次（download_failed / docker_pull_failed）
- on_failure: ask_user（Pulsar2 / BSP 不可获取）
- 要点：验证 Pulsar2 可用 + 准备芯片 C++ BSP/交叉编译器；Pulsar2 / BSP 下载
  ModelScope 优先（`AXERA-TECH/Pulsar2`、`AXERA-TECH/AX650-Community-Hub` 均有），
  无才回退 hf-mirror
- LLM 分支：额外确认 `pulsar2 llm_build2 -h` 可用（Pulsar2 ≥ 6.0，不可用则
  blocked/提示升级镜像）；准备 ax-llm-build 工具（`ensure_axllm_build_tools`，
  默认经 GH_PROXY 克隆 `https://github.com/AXERA-TECH/ax-llm-build.git` 到 cache/）
- 后置：`pulsar2_available` gate → COMPILE
