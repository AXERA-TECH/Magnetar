# TOOLCHAIN（yaml step id: toolchain）

- kind: agent；skill: `.codex/skills/magnetar/hidden/toolchain/SKILL.md`
- depends_on: `stage_review_export`
- inputs: PULSAR2_HOME / PULSAR2_IMAGE / PULSAR2_HF_REPO / TASK_DIR / TARGET_HARDWARE / CXX_BSP_URL / HF_ENDPOINT / GH_PROXY
- outputs: pulsar2_command / cxx_toolchain_file / ax_runtime_root
- timeout: 1200s；retry: 1 次（download_failed / docker_pull_failed）
- on_failure: ask_user（Pulsar2 / BSP 不可获取）
- 要点：验证 Pulsar2 可用（独立包优先：`PULSAR2_HOME` 或
  `~/.cache/magnetar/pulsar2/<版本>/`，无包才回退 Docker 镜像）+ 准备芯片
  C++ BSP/交叉编译器；Pulsar2 下载 ModelScope 优先（`AXERA-TECH/Pulsar2`），
  无才回退 hf-mirror；BSP/runtime 下载地址按芯片从 ax-pipeline
  `scripts/build_common.sh` 解析（`MSP_URL_DEFAULT` / `TOOLCHAIN_URL_DEFAULT`，
  `CXX_BSP_URL`/`CXX_TOOLCHAIN_URL` 可覆盖）
- BSP 公共目录：`magnetar.bsp_util.ensure_bsp(target_hw, cfg)` 自动下载/解压
  BSP 到 `MAGNETAR_BSP_HOME`（默认 `~/.cache/magnetar/bsp`），探测
  `AX_RUNTIME_ROOT`（include/ax_engine_api.h + lib/libax_engine.*）与
  aarch64 交叉编译器，路径固化进 TASK_DIR/config.json
  （`BSP_ROOT` / `AX_RUNTIME_ROOT` / `CXX_TOOLCHAIN`）；AX630C / AX620Q（AX620E
  NPU）的 runtime 与编译器默认同样来自 build_common.sh（ax630c：Arm GNU 9.2
  aarch64；ax620q：ax620q_bsp_sdk uclibc），下载失败才降级 C++
- LLM 分支：额外确认 `pulsar2 llm_build2 -h` 可用（Pulsar2 ≥ 6.0，不可用则
  blocked/提示升级镜像）；准备 ax-llm-build 工具（`ensure_axllm_build_tools`，
  默认经 GH_PROXY 克隆 `https://github.com/AXERA-TECH/ax-llm-build.git` 到 cache/）
- 后置：`pulsar2_available` gate → COMPILE（BSP 缺失仅降级 C++，不阻塞）
