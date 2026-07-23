# Magnetar

将浮点 AI 模型一键转换为 AX 芯片可部署的 AXMODEL 交付包（含 Python/C++ SDK）。

`模型 → ONNX → Pulsar2 编译 → AXMODEL → 仿真验证 → Python/C++ SDK → 交付包`

## 快速开始

**环境**：Linux x86_64，Python 3.10+，Git，Docker，CMake 3.15+。

```bash
git clone https://github.com/AXERA-TECH/Magnetar.git
cd Magnetar
./setup.sh                           # 检查环境依赖
./scripts/install_pulsar2.sh         # Pulsar2 Docker 镜像 (~3 GB)
```

### 方式一：CLI 直接执行（推荐）

```bash
./bin/magnetar exec mobilenet        # MobileNetV2 一跑到底
```

配置固化到 `.magnetarrc`，板端可选：

```bash
cp .magnetarrc.example .magnetarrc
# 编辑填入 TARGET_HARDWARE、BOARD 等
./bin/magnetar exec mobilenet        # 读取 .magnetarrc 自动执行
```

### 方式二：AI Agent 驱动

支持 Codex、Claude、OpenCode 等任意 agent。在 agent 中输入：

```
使用 magnetar，把 SOURCE=https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
转换到 AX650
```

agent 会调用 `./bin/magnetar exec` 执行 pipeline，或按阶段手动推进。

### 交付包产出

```
package/
├── README.md           # 模型概述 + 快速开始
├── models/             # model.axmodel + model_meta.json
├── python/             # Python SDK（pyaxengine）
├── cpp/                # C++ SDK（交叉编译）
├── model_convert/      # 复现脚本（export + compile）
└── reports/            # 性能 + 精度报告
```

没有 AX 板子？不传 `BOARD`，板端验证自动跳过，交付包仍然完整。

### Dry-Run 预览

`.magnetarrc` 中设 `MODE=dry-run`，只扫描不下载不编译。

## CLI 命令

```bash
./bin/magnetar exec <model>          # 直接执行 pipeline（当前支持 mobilenet）
./bin/magnetar run                   # agent 内输出提示，CLI 下直接执行
./bin/magnetar init                  # 创建 .magnetarrc
./bin/magnetar check                 # 检查环境 + 配置
./bin/magnetar status                # 查看任务状态
./bin/magnetar monitor               # TUI 实时流水线
./bin/magnetar report                # 生成 HTML 仪表盘
./bin/magnetar install               # 安装 Pulsar2 Docker 环境
```

## 配置 (.magnetarrc)

```bash
TARGET_HARDWARE=AX650              # AX650 | AX620E
BOARD=root@192.168.1.100           # 可选，不填跳过板端验证
BOARD_PASSWORD=123456              # 板端密码
SDK_LANG=both                      # python | cpp | both
AUTO_APPROVE=false                 # true = 全自动，不暂停
```

完整说明见 `.magnetarrc.example`。

## 工作流

| 阶段 | 说明 | 关键产物 |
|------|------|----------|
| ACQUIRE | 获取模型权重 | `origin/` |
| INIT | 创建隔离工作目录 | `TASK_DIR/` |
| EXPORT | 静态 ONNX + 验证 | `model.onnx`, `model_meta.json` |
| TOOLCHAIN | Pulsar2 + 交叉编译器 | 编译环境就绪 |
| COMPILE | Pulsar2 编译 AXMODEL | `model.axmodel` |
| SIMULATE | ONNX vs AXMODEL 精度对分 | `simulate_report.md` |
| SDK-GEN | Python + C++ SDK | SDK 源码 + 示例 |
| RUNONBOARD | 板端验证（可选） | 精度/延迟/内存报告 |
| PACKAGE | 组装客户交付包 | `package/` |

## 性能参考 (AX650, INT8)

| 模型 | 输入 | AXMODEL | 延迟 | Cosine |
|------|------|---------|------|--------|
| YOLOv8n | 640×640 | ~4 MB | ~8 ms | ≥0.995 |
| YOLOv8s | 640×640 | ~11 MB | ~15 ms | ≥0.995 |
| MobileNetV2 | 224×224 | ~3 MB | ~3 ms | ≥0.998 |

> 你的模型转换完成后，精确数据在 `package/reports/performance_report.md`。

## 工具链

- [Pulsar2](https://hf-mirror.com/AXERA-TECH/Pulsar2) · [pyaxengine](https://github.com/AXERA-TECH/pyaxengine) · [libdet.axera](https://github.com/AXERA-TECH/libdet.axera)
- [AX650 BSP SDK](https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub)

## 常见问题

**没有板子？** 不传 `BOARD`，RUNONBOARD 自动跳过，交付包完整可用。

**中断了？** 重新运行相同 `TASK_DIR`，从断点恢复。

**已有 ONNX？** 直接作为 `SOURCE` 传入，Magnetar 会验证静态 shape 等要求。

**精度不达标？** 自动搜索 `issues/` 中的已知修复，无匹配时 STOP 等你决策。

**编译报 dynamic shape？** Pulsar2 要求静态 ONNX。EXPORT 阶段会自动尝试静态化，失败时 STOP。

**校准数据？** 优先真实数据（≥3 张），也支持从 COCO/ImageNet 自动采样。
