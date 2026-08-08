---
name: toolchain
description: Hidden stage for magnetar. Ensure Pulsar2 and the chip-specific C++ BSP/cross-compilation toolchain are available for compile and SDK validation.
---

# TOOLCHAIN

## 执行
`pulsar_image = magnetar.stages.toolchain.run()`

## LLM 分支（model_route=llm）

- 额外确认 `pulsar2 llm_build2 -h` 可用（Pulsar2 ≥ 6.0）；不可用 → blocked，
  提示升级镜像（`scripts/install_pulsar2.sh` 默认 6.0）；
- 准备 ax-llm-build 工具：`magnetar.stages.llm.ensure_axllm_build_tools(task_dir)`
  （自动克隆 `https://github.com/AXERA-TECH/ax-llm-build.git` 到
  `TASK_DIR/cache/ax-llm-build`）；
- 记录板端 axllm 安装方式（官方 `install.sh`，axllm 分支）到 task.md。

## 验证
- Pulsar2 Docker 镜像可用（`pulsar2 --version` 正常）
- C++ BSP 交叉编译器存在（AX650: BSP SDK V3.10.2；AX620E: Arm GNU 9.2 aarch64）
- LLM 分支：`pulsar2 llm_build2 -h` 正常；ax-llm-build 工具就绪

## STOP
- Pulsar2 不可用且无法从 HF/AXERA-TECH/Pulsar2 获取
- BSP/交叉编译器缺失且无法下载
- LLM 分支：Pulsar2 无 `llm_build2` 且无法升级 → blocked
