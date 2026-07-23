---
name: toolchain
description: Hidden stage for magnetar. Ensure Pulsar2 and the chip-specific C++ BSP/cross-compilation toolchain are available for compile and SDK validation.
---

# TOOLCHAIN

## 执行
`pulsar_image = magnetar.stages.toolchain.run()`

## 验证
- Pulsar2 Docker 镜像可用（`pulsar2 --version` 正常）
- C++ BSP 交叉编译器存在（AX650: BSP SDK V3.10.2；AX620E: Arm GNU 9.2 aarch64）

## STOP
- Pulsar2 不可用且无法从 HF/AXERA-TECH/Pulsar2 获取
- BSP/交叉编译器缺失且无法下载
