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



## 环境安装

Pulsar2 是 Magnetar 工作流的必需工具。如果本地还没有 Docker 和 Pulsar2，使用安装脚本一键部署：

```bash
# 默认安装最新稳定版 Pulsar2 6.0
./scripts/install_pulsar2.sh

# 指定其他版本
PULSAR2_VERSION=5.2 ./scripts/install_pulsar2.sh
```


脚本会自动完成以下步骤：

1. 检测 OS 并安装 Docker（Ubuntu/Debian/CentOS/Fedora）
2. 从 HF 镜像站下载 Pulsar2 Docker 镜像（缓存至 `~/.cache/magnetar/`）
3. 加载镜像并验证 `pulsar2 version`

安装后设置环境变量即可在 Magnetar 工作流中使用：

```bash
export PULSAR2_IMAGE=pulsar2:6.0
```


如需清理或重装，删除镜像和缓存即可：

```bash
docker rmi pulsar2:6.0
rm -rf ~/.cache/magnetar/
```

## 交付物

默认任务目录为 `todos/work/<timestamp>-<model-name>/`，最终交付目录为：

```text
package/
  README.md
  .gitignore
  models/
    model.axmodel
    model_meta.json
  python/          # Python SDK
  cpp/             # C++ SDK
  model_convert/   # ONNX 导出脚本、Pulsar2 配置和转换说明
  reports/
  task.md
  analysis.md
```


`package/` 是客户可直接作为 git 项目管理的目录，结构类似一个完整示例仓库：顶层包含 README、Python/C++ SDK、模型文件、转换复现脚本和验证报告。`model_convert/` 必须记录 ONNX 如何得到、实际使用的 Pulsar2 配置文件、编译命令和校准数据来源。

## 工具链

- Pulsar2 为必需能力，可使用用户环境中的 `pulsar2`、`PULSAR2_BIN` 或 `PULSAR2_IMAGE`；本地没有 Pulsar2 时，从 `https://hf-mirror.com/AXERA-TECH/Pulsar2/tree/main` 获取 Docker 镜像。
- 所有 HuggingFace 下载统一使用 `hf-mirror`，优先设置 `HF_ENDPOINT=https://hf-mirror.com`。
- 所有任务虚拟环境统一用 `uv` 管理：`uv venv` 创建环境，`uv pip install --python <venv>/bin/python ...` 安装依赖。
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
