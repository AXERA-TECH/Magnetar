---
name: toolchain
description: Hidden stage for magnetar. Ensure Pulsar2 and the chip-specific C++ BSP/cross-compilation toolchain are available for compile and SDK validation.
---

# TOOLCHAIN

目标：确认 Pulsar2 可用，并根据 `TARGET_HARDWARE` 准备 C++ SDK 所需的 BSP 或交叉编译工具链。

## Pulsar2

1. 按优先级检查 `PULSAR2_BIN` > `PULSAR2_IMAGE` > `PATH` 中的 `pulsar2` > Docker 镜像。
2. 若均不可用，从 HuggingFace `AXERA-TECH/Pulsar2` 拉取镜像（使用 hf-mirror）。
3. 将可用的 Pulsar2 命令记录为 `pulsar2_command`。

## C++ BSP / 交叉编译工具链

根据 `TARGET_HARDWARE` 选择 BSP 下载地址和 AX runtime 路径：

| 芯片 | BSP 来源 | 内容 |
|------|----------|------|
| AX650 | AX650 BSP SDK V3.10.2 | 含 aarch64 交叉编译器 + AX runtime (include/ lib/) |
| AX620E | Arm GNU 裸工具链（待更新为BSP） | 仅交叉编译器，AX runtime 需另行提供 |

### AX650 BSP SDK

**下载**: 
```
https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub/resolve/main/sdk/edge-computing-AX650_SDK_V3.10.2/02.%20SDK/AX650_SDK_V3.10.2/AX650_SDK_V3.10.2_20260513151335.tgz
```

**HF 页面**: 
```
https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub/tree/main/sdk/edge-computing-AX650_SDK_V3.10.2/02.%20SDK/AX650_SDK_V3.10.2
```

步骤：

1. 若已下载，检查 `TASK_DIR/cache/toolchain/AX650_SDK_V3.10.2/` 是否完整。
2. 若未下载：
   ```
   mkdir -p TASK_DIR/cache/toolchain
   wget -O TASK_DIR/cache/toolchain/AX650_SDK_V3.10.2.tgz <URL>
   tar xzf TASK_DIR/cache/toolchain/AX650_SDK_V3.10.2.tgz -C TASK_DIR/cache/toolchain/
   ```
3. 探索 BSP 目录结构，定位：
   - 交叉编译器路径（如 `arm-linux-gnueabihf-g++` 或 `aarch64-none-linux-gnu-g++` 所在目录）。
   - AX runtime 路径：包含 `include/` 和 `lib/`（如 `libax_engine.so` 或 `libaxengine.so`）。
4. 记录路径：
   - `CXX_COMPILER_PATH`: 交叉编译器 bin 目录
   - `AX_RUNTIME_ROOT`: AX runtime 根目录（含 include/ 和 lib/）
5. 生成 `sdk/cpp/toolchain-aarch64.cmake`，配置：
   - `CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` 指向交叉编译器。
   - `AX_RUNTIME_ROOT` 变量指向 AX runtime 路径。

### AX620E（暂用 Arm GNU 裸工具链）

1. 检查 `aarch64-none-linux-gnu-g++` 或 `aarch64-linux-gnu-g++`。
2. 如不存在，下载默认 URL：
   ```
   https://developer.arm.com/-/media/Files/downloads/gnu-a/9.2-2019.12/binrel/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz
   ```
3. 解压到 `TASK_DIR/cache/toolchain/gcc-arm-9.2-2019.12/`。
4. 生成 `sdk/cpp/toolchain-aarch64.cmake`。
5. AX620E 的 `AX_RUNTIME_ROOT` 需由用户另行提供，不可用 BSP 路径。

## 验证

- Pulsar2 可用（可执行 `pulsar2` 或 `docker run` 成功）。
- 若 TARGET_HARDWARE=AX650：BSP 已下载并解压，`CXX_COMPILER_PATH` 和 `AX_RUNTIME_ROOT` 已定位。
- 若 TARGET_HARDWARE=AX620E：交叉编译器可用或已下载。
- `sdk/cpp/toolchain-aarch64.cmake` 已生成。

## STOP

- Pulsar2 不可用且无法从任意来源获取。
- AX650 BSP 下载失败，且无法从备用 URL 获取。
- AX620E 交叉编译器下载失败，且用户未提供替代。
