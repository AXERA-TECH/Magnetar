---
name: toolchain
description: Hidden stage for magnetar. Ensure Pulsar2 and the aarch64 C++ cross-compilation toolchain are available for compile and SDK validation.
---

# TOOLCHAIN

目标：确认 Pulsar2 可用，并准备 C++ SDK 交叉编译工具链。

## Pulsar2

Pulsar2 是必需能力。按顺序检查：

1. `PULSAR2_BIN` 指定的本地可执行文件。
2. 当前 PATH 中的 `pulsar2`。
3. `PULSAR2_IMAGE` 指定的 Docker 镜像。
4. 用户环境已有 AXERA Pulsar2 发布包。
5. 本地没有 Pulsar2 时，设置 `HF_ENDPOINT=https://hf-mirror.co`，从 `https://hf-mirror.co/AXERA-TECH/Pulsar2/tree/main` 获取 Docker 镜像或镜像包，并记录下载方式、镜像名和 digest。

不得把 Arm GNU 工具链压缩包当作 Pulsar2。若本地 Pulsar2 与 HuggingFace fallback 都不可用，STOP 并要求用户提供镜像、二进制路径或安装包。所有 HuggingFace fallback 下载必须走 `hf-mirror`，不得直接使用 `huggingface.co` 作为下载端点。

## C++ 交叉编译工具链

默认 URL：

```text
https://developer.arm.com/-/media/Files/downloads/gnu-a/9.2-2019.12/binrel/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz
```

步骤：

1. 检查 `aarch64-none-linux-gnu-g++` 或 `aarch64-linux-gnu-g++`。
2. 如不存在，下载默认 URL 到 `TASK_DIR/cache/toolchain/`。
3. 解压到 `TASK_DIR/cache/toolchain/gcc-arm-9.2-2019.12/`。
4. 生成 `sdk/cpp/toolchain-aarch64.cmake`。
5. 记录版本和路径到 `task.md`。

## 降级

C++ 工具链下载失败时，允许降级为只验证 `cmake configure`，但必须在 `analysis.md` 和最终 README 中说明。
