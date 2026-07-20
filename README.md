# Magnetar

将远程或本地的浮点 AI 模型一键转换为 AX 芯片可部署的 AXMODEL 交付包（含 Python/C++ SDK）。

`模型 → ONNX → Pulsar2 编译 → AXMODEL → 仿真验证 → Python/C++ SDK → 客户交付包`

## 前提条件

| 依赖 | 用途 | 安装 |
|------|------|------|
| Git | 版本管理 | 系统自带或 `apt install git` |
| Python 3.8+ | 模型导出、SDK | 系统自带或 `apt install python3` |
| uv | Python 虚拟环境管理 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Docker | Pulsar2 编译运行 | `curl -fsSL https://get.docker.com \| sh` |
| CMake 3.15+ | C++ SDK 构建 | `apt install cmake` |
| AX 开发板 (AX650/AX620E) | 板端验证（可选） | 联系爱芯获取 |
## 版本兼容性

| 组件 | 最低版本 | 推荐版本 |
|------|----------|----------|
| Codex | 最新稳定版 | — |
| Python | 3.8 | 3.10+ |
| uv | 0.1.0 | 最新版 |
| Docker | 20.10 | 24.0+ |
| CMake | 3.15 | 3.22+ |
| Pulsar2 | 6.0 | 6.0 |
| AX650 BSP SDK | V3.10.2 | V3.10.2 |
| onnxruntime | 1.14 | 1.17+ |
| pyaxengine | latest | latest |

> 仅支持 Linux 主机（x86_64）。macOS/Windows 用户可通过 Docker 或远程 Linux 服务器使用。


## 安装

```bash
git clone https://github.com/AXERA-TECH/Magnetar.git
cd Magnetar
./setup.sh
```

setup.sh 会自动检查环境依赖并给出缺失项的安装命令。

安装 Pulsar2 编译环境（Docker 镜像，约 3 GB）：

```bash
./scripts/install_pulsar2.sh
```

重启 Codex 后生效。

## 快速开始

以下示例将一个 **YOLOv8n** 目标检测模型从 PyTorch 权重转换到 AX650 芯片的 AXMODEL 交付包。

### 1. 初始化项目配置

```bash
cp .magnetarrc.example .magnetarrc
# 编辑 .magnetarrc 填入你的配置
```

### 2. 在 Codex 中启动转换

```
$magnetar
SOURCE=https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
TARGET_HARDWARE=AX650
BOARD=root@192.168.1.100
```

工作流会自动完成 9 个阶段，你可在每个阶段结束时确认是否继续。


### 只想预览不执行？

使用 dry-run 模式只扫描模型、检查环境、输出预估计划，不下载大文件也不编译：

```bash
# .magnetarrc 中设置
MODE=dry-run
```

或在 Codex 中说：

```
$magnetar --dry-run
SOURCE=https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
TARGET_HARDWARE=AX650
```

### 3. 拿到交付包

```
package/
  README.md           # 模型概述 + 快速开始
  models/
    model.axmodel      # 芯片可部署模型
    model_meta.json    # 输入/输出元信息
  python/
    yolov8n_sdk/       # Python SDK（基于 pyaxengine）
    example.py
  cpp/
    CMakeLists.txt     # C++ SDK（可直接交叉编译）
  model_convert/
    export_onnx.py     # 复现 ONNX 导出
    compile_pulsar2.sh # 复现 AXMODEL 编译
  reports/
    performance_report.md
```

## 工作流阶段

| 阶段 | 说明 | 关键产物 |
|------|------|----------|
| ACQUIRE | 获取模型权重到本地 | `origin/` 目录 + 候选文件清单 |
| INIT | 创建隔离工作目录 | `TASK_DIR/` + `task.md` + `analysis.md` |
| EXPORT | 导出静态 ONNX 并验证 | `model.onnx` + `model_meta.json` + 校准数据 |
| TOOLCHAIN | 准备 Pulsar2 + BSP/交叉编译器 | Pulsar2 可用 + `toolchain-aarch64.cmake` |
| COMPILE | Pulsar2 编译 AXMODEL | `model.axmodel` + 编译报告 |
| SIMULATE | ONNX vs AXMODEL 精度对分 | `simulate_report.md`（cosine ≥ 0.99） |
| SDK-GEN | 生成 Python + C++ SDK | SDK 源码 + 示例 + README |
| RUNONBOARD | 板端真实运行验证 | 精度/延迟/内存报告 |
| PACKAGE | 组装最终客户交付包 | `package/` 目录 |

## 支持的模型

已验证可完整走通流程的模型架构：

| 模型类型 | 架构示例 | 任务 |
|----------|----------|------|
| YOLO 检测 | YOLOv5/v8/v11 | 目标检测 |
| YOLO 姿态 | YOLOv8-pose, YOLO11-pose | 姿态估计 |
| MobileNet | MobileNetV2/V3 | 图像分类 |
| 语音合成 | MeloTTS, Kokoro | TTS |
| 语音识别 | F5-TTS | ASR |

> 未列出的模型也可以尝试。Magnetar 会从 PyTorch/HuggingFace/ONNX 出发自动检测导出路径。如果自动检测失败，会在相应阶段 STOP 并给出诊断信息。

## 性能参考

以下数据基于 AX650 芯片实测（Pulsar2 6.0，INT8 量化）：

| 模型 | 输入尺寸 | AXMODEL 大小 | 推理延迟 | 仿真 cosine |
|------|----------|-------------|----------|-------------|
| YOLOv8n | 640×640 | ~4 MB | ~8 ms | ≥ 0.995 |
| YOLOv8s | 640×640 | ~11 MB | ~15 ms | ≥ 0.995 |
| MobileNetV2 | 224×224 | ~3 MB | ~3 ms | ≥ 0.998 |

> 实际性能因具体权重、校准数据和编译配置不同而异。你的模型转换完成后会在 `package/reports/performance_report.md` 中得到精确数据。


## 项目配置文件

在仓库根目录创建 `.magnetarrc` 可固化常用参数，避免每次重复输入：

```bash
# 优化目标芯片: AX650 | AX620E
TARGET_HARDWARE=AX650

# 板端 SSH 信息（可选，不填则跳过板端验证）
BOARD=root@192.168.1.100
BOARD_PASSWORD=123456

# Pulsar2 Docker 镜像（可选）
PULSAR2_IMAGE=pulsar2:6.0

# SDK 语言: python | cpp | both
SDK_LANG=both

# 是否自动通过各阶段审批（true 则全自动运行）
AUTO_APPROVE=false
```

参照 `.magnetarrc.example`。

## 常见问题

**Q: 没有 AX 开发板能用吗？**
A: 可以。不填 `BOARD` 即可跳过板端验证阶段（RUNONBOARD），交付包中会标注该阶段为 N/A。你仍然可以获得完整的 AXMODEL + SDK 产物。

**Q: Pulsar2 Docker 镜像下载太慢？**
A: 国内默认走 hf-mirror。海外用户可在 `.magnetarrc` 中自行指定 Pulsar2 镜像，或设置环境变量 `PULSAR2_IMAGE=<your-image>`。

**Q: uv 是什么，必须装吗？**
A: uv 是快速的 Python 包管理器。Magnetar 用它隔离每个任务的 Python 环境，避免污染系统 Python。安装只需一条命令：
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Q: 编译报错 "dynamic shape not supported"？**
A: Pulsar2 要求 ONNX 为静态 shape。Magnetar 会在 EXPORT 阶段自动检测并尝试静态化。如果自动静态化失败，需要你在导出时手动固定 batch size 和输入尺寸。

**Q: 仿真精度 cosine < 0.99 怎么办？**
A: Magnetar 会自动搜索 `issues/` 目录中的已知修复方案并尝试应用。如果没有匹配方案，会在 SIMULATE 阶段 STOP，由你决定是否接受当前精度或调整编译参数。

**Q: 如何只编译不上板？**
A: `.magnetarrc` 中 `BOARD=` 留空，工作流会在 RUNONBOARD 阶段自动跳过。

**Q: 中断后能恢复吗？**
A: 所有中间产物保留在 `todos/work/<timestamp>-<model>/` 中。重新运行并指定相同的 `TASK_DIR`，Magnetar 会尝试从已有产物恢复。
**Q: 如何从已有 ONNX 开始？**
A: 将 ONNX 文件作为 SOURCE 传入即可。Magnetar 仍会执行完整的 ACQUIRE 和 EXPORT 验证流程，确保 ONNX 符合 Pulsar2 静态 shape 要求。

**Q: 校准数据从哪来？**
A: 优先使用真实业务数据（≥3 张）。Magnetar 也支持从 COCO/ImageNet 等公开数据集自动采样生成校准集——在 EXPORT 阶段选择"自动采样"即可。

**Q: 下载大文件失败怎么办？**
A: BSP SDK 和 Docker 镜像支持断点续传。模型文件下载失败时，ACQUIRE 阶段会自动重试 2 次。你也可以手动下载后放到 `TASK_DIR/origin/` 再重新运行。

**Q: 多个模型能一次处理吗？**
A: 目前每个 Magnetar 运行处理一个模型。如果需要批量处理多个模型，可以编写脚本多次调用，或等待后续的批量模式支持。

## 工具链

- **Pulsar2**: [hf-mirror.com/AXERA-TECH/Pulsar2](https://hf-mirror.com/AXERA-TECH/Pulsar2)
- **pyaxengine**: [github.com/AXERA-TECH/pyaxengine](https://github.com/AXERA-TECH/pyaxengine)
- **libdet.axera**: [github.com/AXERA-TECH/libdet.axera](https://github.com/AXERA-TECH/libdet.axera) (YOLO 后处理)
- **AX650 BSP SDK**: [hf-mirror.com/AXERA-TECH/AX650-Community-Hub](https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub)

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CODEX_HOME` | `~/.codex` | Codex 安装目录 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像（国内默认） |
| `PULSAR2_VERSION` | `6.0` | Pulsar2 Docker 镜像版本 |
| `MAGNETAR_BOARD_PASSWORD` | `123456` | 板端默认密码 |
| `MAGNETAR_TASK_DIR` | `todos/work/<ts>-<model>/` | 覆盖默认任务目录 |

## 测试

```bash
python -m unittest discover -s tests
```
