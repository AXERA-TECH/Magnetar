# AGENTS.md

本仓库包含 Magnetar 模型部署工具。所有 Agent 回复默认使用中文。

## 项目目标

将远程或本地浮点模型转换为 AX 芯片客户交付包：

`模型 → ONNX → Pulsar2 编译 → AXMODEL → 仿真验证 → Python/C++ SDK → 交付包`

## 工具库

Agent 负责编排和决策。`magnetar/stages/*.py` 提供确定性执行函数：

| 模块 | 函数 | 用途 |
|------|------|------|
| `magnetar.config` | `load_config()` | 读取 `.magnetarrc` + 环境变量 |
| `magnetar.docker_util` | `latest_pulsar2_image()`, `docker_pulsar2()` | Docker/Pulsar2 封装 |
| `magnetar.board_util` | `select_board()`, `ssh()`, `scp_to()`, `scp_from()` | AX 板端操作 |
| `magnetar.stages.init` | `run(config)` → `task_dir` | 创建 TASK_DIR 结构 |
| `magnetar.stages.acquire` | `run(task_dir, source)` | 获取模型到 origin/ |
| `magnetar.stages.export` | `run_mobilenet(task_dir)` → `sample` | MobileNet ONNX 导出+验证+校准 |
| `magnetar.stages.toolchain` | `run()` → `pulsar_image` | 验证 Pulsar2 Docker 可用 |
| `magnetar.stages.compile` | `run(task_dir, target_hw, image)` | Pulsar2 编译 AXMODEL |
| `magnetar.stages.simulate` | `run(task_dir, sample, image)` → `metrics` | ONNX vs AXMODEL 精度对分 |
| `magnetar.stages.sdk_gen` | `run_mobilenet_python()`, `run_mobilenet_cpp()` | 生成 Python/C++ SDK |
| `magnetar.stages.runonboard` | `run(task_dir, sample, hw, pwd)` → `metrics` | 板端部署验证 |
| `magnetar.stages.package` | `assemble(task_dir, metrics, image)` → `pkg` | 组装交付包 |

非 MobileNet 模型：Agent 需自行实现 ONNX 导出逻辑并正确填写 `model_meta.json`。

## 执行流程

严格按以下顺序推进 9 阶段，不可跳过：

```
1. INIT      → magnetar.stages.init.run(config)
2. ACQUIRE   → magnetar.stages.acquire.run(task_dir, source)
3. EXPORT    → 模型特定导出 + 生成 model_meta.json + 校准数据
4. TOOLCHAIN → magnetar.stages.toolchain.run()
5. COMPILE   → magnetar.stages.compile.run(task_dir, target_hw, image)
6. SIMULATE  → metrics = simulate.run(task_dir, sample, image)
7. SDK-GEN   → 生成 Python/C++ SDK
8. RUNONBOARD→ 若 BOARD 已配置则执行，否则跳过
9. PACKAGE   → magnetar.stages.package.assemble(task_dir, metrics, image)
```

每阶段完成后更新 `TASK_DIR/task.md` 和 `analysis.md`。

## STOP 点

必须暂停并等待用户确认：

- `SOURCE`、`TARGET_HARDWARE` 未提供
- 主模型文件或导出入口无法自动判断
- ONNX 与原模型对分失败（cosine < 0.99）
- Pulsar2 不可用
- 编译失败需要修改模型图
- SIMULATE 精度不达标（先查 `issues/` 目录）
- 需要私有凭据

BOARD 缺失不是 STOP——自动跳过 RUNONBOARD。

## 配置

优先读取仓库根目录 `.magnetarrc`（shell 风格 key=value），环境变量可覆盖。

```bash
SOURCE=<模型路径/URL>          # 必填
TARGET_HARDWARE=AX650          # AX650 | AX620E
BOARD=root@192.168.1.100       # 可选，不填跳过板端验证
BOARD_PASSWORD=123456          # 板端密码
SDK_LANG=both                  # python | cpp | both
MODE=full                      # full | dry-run
```

详见 `.magnetarrc.example`。

## 目录约定

默认任务目录 `todos/work/<timestamp>-<model-name>/`：

```
TASK_DIR/
  origin/       # 原始模型
  export/       # ONNX + model_meta.json + 校准数据
  compile/      # Pulsar2 配置 + model.axmodel
  simulate/     # 精度对分报告
  sdk/python/   # Python SDK
  sdk/cpp/      # C++ SDK
  runonboard/   # 板端验证
  package/      # 客户交付包
  cache/        # 跨阶段中间文件
  task.md       # 任务记录
  analysis.md   # 分析记录
```

产物不得污染原始模型工程。中间文件写入 TASK_DIR。

## 验证期望

- ONNX 导出必须生成可复现脚本，Torch/ONNX 对分
- Pulsar2 配置 `highest_mix_precision` 必须为 false
- 精度验证：cosine ≥ 0.99，MAE 等任务相关指标
- Python SDK import 检查通过，用 `pyaxengine.AxEngineExecutionProvider`
- C++ SDK cmake configure 通过
- `ax_run_model` 只用于 smoke check，不能替代 SDK 验证
- PACKAGE 产出独立 git 项目目录

## 爱芯开发知识

- Pulsar2 镜像: https://hf-mirror.com/AXERA-TECH/Pulsar2
- Pulsar2 文档: https://pulsar2-docs.readthedocs.io/zh-cn/latest/
- 爱芯 HF 模型: https://hf-mirror.com/AXERA-TECH
- 爱芯 GitHub: https://github.com/AXERA-TECH
- AX650 BSP SDK: https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub
- 本机 Docker 可能已安装 Pulsar2，优先使用最新版本
- 上板运行可用 `remote-infer` skill（若在 Codex 中）
- LLM 编译: https://github.com/AXERA-TECH/ax-llm
- 调试问题记录到 `issues/` 下，命名 `序号_模型名_阶段_问题简述.md`
