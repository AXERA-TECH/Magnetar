# Magnetar

Magnetar 是一套面向 AX 芯片部署的模型转换工作流，目标是帮助用户完成：

`远程或本地模型 -> ONNX -> Pulsar2 编译 -> AXMODEL -> 仿真验证 -> Python/C++ SDK -> 客户交付包`

# 快速开始

## Codex

本仓库提供项目级 Codex 规则和可复用 skill：

- `AGENTS.md`: Codex 进入本仓库后的默认约束。
- `.codex/skills/magnetar/SKILL.md`: Magnetar AXMODEL 转换与 SDK 生成工作流。
- `workflows/magnetar.yaml`: 机器可读工作流规范。

在 Codex 中可以直接说：

```text
使用 magnetar，把 SOURCE=[本地路径/Git/HuggingFace/URL] 转换到 AX650，并输出 Python/C++ SDK
```

安装到当前用户的 Codex skill 目录：

```bash
./setup.sh
```

默认安装到 `${CODEX_HOME:-~/.codex}/skills/magnetar`。开发时如需使用仓库内文件的软链接：

```bash
./setup.sh --link --force
```

## 交付物

默认任务目录为 `todos/work/<timestamp>-<model-name>/`，最终交付目录为：

```text
package/
  models/
    model.axmodel
    model_meta.json
  sdk/
    python/
    cpp/
  reports/
  README.md
  task.md
  analysis.md
```

## 工具链

- Pulsar2 为必需能力，可使用用户环境中的 `pulsar2`、`PULSAR2_BIN` 或 `PULSAR2_IMAGE`；本地没有 Pulsar2 时，从 `https://huggingface.co/AXERA-TECH/Pulsar2/tree/main` 获取 Docker 镜像。
- C++ SDK 默认使用 Arm GNU aarch64 工具链：
  `https://developer.arm.com/-/media/Files/downloads/gnu-a/9.2-2019.12/binrel/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz`
- Python SDK 使用 `pyaxengine`：`https://github.com/AXERA-TECH/pyaxengine`，默认 provider 为 `AxEngineExecutionProvider`。
- C++ SDK 直接链接 AX Engine runtime（常见库名为 `libax_engine.so`/`libax_sys.so`，厂商包也可能使用 `libaxengine.so` 等价命名），必须在主机交叉编译后上板运行。
- `ax_run_model` 只用于 AXMODEL 格式和最小运行 smoke check，不能作为 Python/C++ SDK 的实现。

## 测试

运行真实 MobileNet 工作流集成测试：

```bash
python -m unittest discover -s tests
```

该测试会下载 torchvision MobileNetV2 权重，导出静态 ONNX，调用本地最新语义版本 `pulsar2:*` Docker 镜像编译 AXMODEL，执行 `pulsar2 run` 仿真，生成 Python/C++ SDK，选择与 `MAGNETAR_TARGET_HARDWARE` 匹配的 AX 板，上传交付包，并真实运行 Python SDK 与交叉编译后的 C++ SDK。产物位于 `todos/work/unittest-mobilenet-real/package/`。

常用环境变量：

- `MAGNETAR_TARGET_HARDWARE`: 默认 `AX650`。
- `MAGNETAR_BOARD`: 可选，指定 `user@host[:port]`；未指定时测试从 dashboard 选择空闲且芯片匹配的板。
- `MAGNETAR_BOARD_PASSWORD`: 默认 `123456`。
- `MAGNETAR_BOARD_DASHBOARD`: 默认 `http://10.126.35.22:25000/api/devices`。
- `AARCH64_GXX`: 可选，指定 aarch64 交叉编译器路径。
