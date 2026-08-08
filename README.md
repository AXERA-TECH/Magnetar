# Magnetar

将浮点 AI 模型一键转换为 AX 芯片可部署的 AXMODEL 交付包（含 Python/C++ SDK）。

`模型 → ONNX → Pulsar2 编译 → AXMODEL → 仿真验证 → Python/C++ SDK → 交付包 → 发布`

## 快速开始

**环境**：Linux x86_64，Python 3.10+，Git，Docker，CMake 3.15+。

```bash
git clone https://github.com/AXERA-TECH/Magnetar.git
cd Magnetar
./setup.sh                           # 检查环境依赖
./scripts/install_pulsar2.sh         # Pulsar2 Docker 镜像 (~3 GB)
```

### 通过 AI Agent 使用

支持 **Codex**、**Claude Code**、**OpenCode** 等任意 Agent。在 Agent 中输入：

```
使用 magnetar，把 SOURCE=https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
转换到 AX650
```

Agent 会读取 `AGENTS.md`（所有 Agent 的统一入口），按 10 阶段自动推进。

不想每次手输参数？创建配置文件固化：

```bash
cp .magnetarrc.example .magnetarrc
```

没有 AX 板子？不传 `BOARD`，板端验证自动跳过，交付包仍然完整。

**LLM / 自回归模型**（Qwen、Llama、MiniCPM、GPT、含 LLM 骨干的 TTS 等）：
工作流会自动改走 **ax-llm** 路径——`pulsar2 llm_build2` 直接编译 HuggingFace 权重为
逐层 AXMODEL，板端用 `axllm serve` 提供 OpenAI 兼容 API，交付 Python SDK 仅依赖
`requests`。无需手动指定，INIT 后的 `model_route` gate 自动判定。

### 交付包产出

```
package/
├── README.md           # 极简两步上手
├── setup.sh            # 一键安装依赖
├── run.sh              # 一键运行推理
├── models/             # model.axmodel + model_meta.json
├── python/             # Python SDK（pyaxengine）
├── cpp/                # C++ SDK（交叉编译）
├── model_convert/      # 复现脚本（export + compile）
└── reports/            # 性能 + 精度报告
```

PACKAGE 完成后进入 PUBLISH 阶段：Agent 会问你**发布到哪（GitHub/HF）、仓库名、凭据**，然后自动推送。

### Dry-Run 预览

`.magnetarrc` 中设 `MODE=dry-run`，只扫描不下载不编译。

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
| PUBLISH | 发布到 GitHub / HuggingFace | repo URL |

## 通用 ONNX 导出（非 MobileNet 模型）

EXPORT 阶段默认走 `magnetar/export_onnx.py` 通用导出器：**先尝试最简单路径
`torch.onnx.export(dynamo=False)`，失败后自动逐级降级**（opset 13/11 →
dynamo/`torch.export` → onnxsim 后处理），并记录每一步失败原因。成功后自动完成
ONNX Runtime 对分（cosine ≥ 0.99）、静态 shape 检查、`model_meta.json`、
校准数据与 `export_report.md`；全部路径失败时抛出带诊断报告的 `ExportError`，
Agent 依据报告决定人工处理方向。

最普适的用法是写一个 load 脚本（定义 `build()` 返回 `(model, example_inputs)`）：

```bash
python scripts/export_onnx.py --task-dir todos/work/demo \
    --load-script /path/to/load.py --model-name demo
```

也支持架构名快速导出（配合权重）：

```bash
python scripts/export_onnx.py --task-dir todos/work/demo \
    --arch torchvision:mobilenet_v2 --checkpoint weights.pt \
    --input-shapes 1x3x224x224 --model-name demo
```

Python API：`magnetar.stages.export.run_generic(task_dir, model=..., example_inputs=...)`
或直接 `magnetar.export_onnx.export_to_onnx(...)`。load 脚本约定见
`scripts/export_onnx.py --help`。

## 通用 SDK 生成（非 MobileNet）

SDK-GEN 阶段对非 MobileNet 模型优先调用 `magnetar.stages.sdk_gen.run_generic_python(task_dir)`
和 `run_generic_cpp(task_dir)`，基于两份文件生成：

- `export/model_meta.json`：模型接口权威（输入输出名/shape/dtype，AXMODEL 即按此编译）
- `origin/model_flow.json`：ACQUIRE 阶段记录的运行流程（真实样本、预处理/后处理代码）

一致性由生成器强制保障：示例样本缺失或预处理/后处理代码语法错误会直接报错，
避免生成与 ACQUIRE 验证过的运行流程不一致的 SDK。自定义预处理/后处理只需在
`model_flow.json` 提供代码后重新生成。

**发布版约束**：端到端 NPU 验证通过（RUNONBOARD 报告存在）后，`package/assemble()`
自动把交付包内 SDK 替换为 NPU 专用版——只依赖 `numpy + pyaxengine`，
不含 onnxruntime/torch/transformers 回退；源目录保留开发版供本机验证。

## 性能参考 (AX650, INT8)

| 模型 | 输入 | AXMODEL | 延迟 | Cosine |
|------|------|---------|------|--------|
| YOLOv8n | 640×640 | ~4 MB | ~8 ms | ≥0.995 |
| YOLOv8s | 640×640 | ~11 MB | ~15 ms | ≥0.995 |
| MobileNetV2 | 224×224 | ~3 MB | ~3 ms | ≥0.998 |

> 你的模型转换完成后，精确数据在 `package/reports/performance_report.md`。

## 可视化监控

```bash
./bin/magnetar monitor              # TUI 实时流水线
./bin/magnetar report               # 生成 HTML 仪表盘
```

## Agent 兼容

`AGENTS.md` 是所有 AI Agent 的统一工作流入口：

| Agent | 入口文件 | 说明 |
|-------|----------|------|
| Codex | `AGENTS.md` + `.codex/skills/magnetar/SKILL.md` | SKILL.md 委托到 AGENTS.md |
| Claude Code | `CLAUDE.md` → `AGENTS.md` 符号链接 | 直接读取 |
| OpenCode | `AGENTS.md` | 直接读取 |

工具函数位于 `magnetar/stages/*.py`，Agent 负责编排决策，函数负责确定性执行。

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
