---
name: magnetar
description: Convert remote or local AI models into AXera AXMODEL packages with Python and C++ SDKs for customer delivery. Use when Codex must acquire a model from Git/HuggingFace/URL/local path, export ONNX, compile with Pulsar2, simulate/validate AXMODEL accuracy, optionally run on AX hardware, generate SDKs, or package deployment artifacts.
---

# Magnetar

始终用中文沟通。该 skill 是 Magnetar 的公开入口，用于把远程或本地模型转换为客户可用的 AXMODEL 交付包。

严格按以下顺序推进：
## 项目配置文件 (.magnetarrc)

启动时先检查仓库根目录是否存在 `.magnetarrc` 文件。若存在，按 shell 风格 key=value 逐行解析，将值作为对应参数的默认值。

支持的配置项：

| Key | 对应参数 | 说明 |
|-----|----------|------|
| `SOURCE` | SOURCE | 模型来源 |
| `TARGET_HARDWARE` | TARGET_HARDWARE | 目标芯片 |
| `MODEL_NAME` | MODEL_NAME | 模型名称 |
| `TASK_DIR` | TASK_DIR | 工作目录 |
| `SDK_LANG` | SDK_LANG | SDK 语言 |
| `BOARD` | BOARD | 板端 SSH |
| `BOARD_PASSWORD` | BOARD_PASSWORD | 板端密码 |
| `PULSAR2_IMAGE` | PULSAR2_IMAGE | Pulsar2 Docker 镜像 |
| `PULSAR2_BIN` | PULSAR2_BIN | Pulsar2 本地二进制 |
| `CXX_BSP_URL` | CXX_BSP_URL | BSP 下载地址 |
| `HF_TOKEN` | HF_TOKEN | HF 私有凭据 |
| `HF_ENDPOINT` | HF_ENDPOINT | HF 镜像端点 |
| `AUTO_APPROVE` | — | 行为选项（见下文） |

已通过 `.magnetarrc` 或环境变量提供有效值的参数，不再向用户提问。`.magnetarrc` 中 `SOURCE`、`TARGET_HARDWARE` 均配置且有效时，可直接跳过交互进入执行。

### 逐阶段审批

每个主要阶段（ACQUIRE、EXPORT、COMPILE、SIMULATE、RUNONBOARD、PACKAGE）完成后，默认暂停并展示阶段摘要，等待用户确认后再进入下一阶段。用户可回复"继续"推进，或"调整"返回修改。

若 `.magnetarrc` 中 `AUTO_APPROVE=true`，则跳过所有审批暂停，全自动执行到底。

### Dry-Run 模式

`.magnetarrc` 中设置 `MODE=dry-run` 或用户在 Codex 中指定 `--dry-run` 时，工作流进入预览模式：

- ACQUIRE：仅扫描 SOURCE 的元信息（文件列表、大小），不下载大文件
- INIT：创建 TASK_DIR 和审计文件
- 后续阶段：仅输出预估计划（检测到的导出路径、编译配置、预估耗时），不实际执行

Dry-run 完成后输出完整计划供用户审阅，用户确认后可通过设置 `MODE=full` 重新运行实际转换。



## 阶段不可跳过

所有 9 个阶段必须全部遍历，不可跳过。即使用户直接提供了 ONNX 模型文件，ACQUIRE 和 EXPORT 阶段同样必须执行，按各阶段的产物和验证要求完成全量检查：

- ACQUIRE 必须产出来源记录和候选文件清单，即使 SOURCE 是单个 ONNX 文件。
- EXPORT 必须完成 ONNX checker、ONNX Runtime 加载、model_meta.json、校准数据和导出报告，即使模型本身已经是 ONNX 格式。
- 跳过任一阶段会导致后续产物缺失（如 manifest.json、model_meta.json、校准数据），最终 PACKAGE 交付包将不满足客户从零复现的要求。


`ACQUIRE -> INIT -> EXPORT -> TOOLCHAIN -> COMPILE -> SIMULATE -> SDK-GEN -> RUNONBOARD -> PACKAGE`

RUNONBOARD 阶段的行为取决于 `BOARD` 是否提供：
- **提供了 BOARD**：RUNONBOARD 正常执行，在板端验证模型精度、延迟和内存。
- **未提供 BOARD**：RUNONBOARD 自动跳过，`runonboard_report.md` 标记各指标为 N/A，`performance_report.md` 中板端相关数据标注为 N/A。交付包仍然完整可用。

机器可读规范见 [../../../workflows/magnetar.yaml](../../workflows/magnetar.yaml)。

### 断点恢复

如果工作流中断（手动停止、网络故障、OOM 等），可重新运行并指定相同的 `TASK_DIR` 或 `MODEL_NAME`（使默认 TASK_DIR 匹配）：

- Magnetar 会检查 `TASK_DIR` 中已有的阶段产物，从第一个缺失产物的阶段继续
- 已完成的阶段不会重复执行
- `task.md` 中记录每次运行的状态和中断点

## 输入

- `SOURCE`: 必填。Git 仓库、HuggingFace repo、本地目录、单模型文件或可下载 URL。
- `TARGET_HARDWARE`: 必填。默认支持 `AX650`、`AX620E`，其他 AX 芯片需确认 Pulsar2 支持。
- `MODEL_NAME`: 可选。默认从 `SOURCE` 推断。
- `TASK_DIR`: 可选。默认 `todos/work/<timestamp>-<model-name>/`。可通过环境变量 `MAGNETAR_TASK_DIR` 全局覆盖默认前缀目录。
- `SDK_LANG`: 可选。`python`、`cpp`、`both`，默认 `both`。
- `HF_TOKEN`: 条件必填。私有 HuggingFace 模型从环境变量读取。
- `BOARD`: 可选。板端 SSH 信息，格式 `user@host[:port]`。不填则跳过 RUNONBOARD 阶段，交付包中板端数据标注 N/A。
- `BOARD_PASSWORD`: 条件必填。提供 BOARD 时需密码，默认 `123456`。不提供 BOARD 时忽略。
- `PULSAR2_IMAGE` 或 `PULSAR2_BIN`: 可选。Pulsar2 Docker 镜像或本地可执行文件；本地没有 Pulsar2 时，默认从 `https://hf-mirror.com/AXERA-TECH/Pulsar2/tree/main` 获取 Docker 镜像。
- `CXX_BSP_URL`: 可选。C++ BSP SDK 下载地址，含交叉编译器和 AX runtime。默认按目标芯片选择：
  - AX650: `https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub/resolve/main/sdk/edge-computing-AX650_SDK_V3.10.2/02.%20SDK/AX650_SDK_V3.10.2/AX650_SDK_V3.10.2_20260513151335.tgz`
  - AX620E: `https://developer.arm.com/-/media/Files/downloads/gnu-a/9.2-2019.12/binrel/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz`（待更新为BSP）


## 关键校准对齐规则

Pulsar2 校准与 libdet 推理的归一化公式不同：

| 组件 | 公式 |
|------|------|
| Pulsar2 校准 | `(img - mean) / calibration_std` |
| libdet.axera | `(input - mean) * std` |

ONNX 模型默认期望 [0,1] 输入时：
- Pulsar2 `calibration_std` = **255**（uint8/255=[0,1]）
- libdet `std` = **1/255**（uint8×(1/255)=[0,1]）

> 常见错误：`calibration_std=0.004` 导致校准输入 [0,65025]，推理输出全零。

## 分发策略

| 平台 | 内容 | 用途 |
|------|------|------|
| GitHub | 源码 + CMake + model_convert | 从零构建复现 |
| GitHub Release | 预编译 bin/lib | 直接下载 |
| HuggingFace | 预编译模型 + 仅 binaries | 开箱即用推理 |

HF 不含 model_convert/ 和 C++ 源码；HF README 需 YAML frontmatter。

## 输出

最终交付目录为 `TASK_DIR/package/`，必须是一份客户拿到后能从零复现模型转换并运行 Python/C++ SDK 的完整交付包：

```text
package/
  README.md           # 顶层入口：模型概述、快速开始（推理/转换两条路径）、目录说明
  .gitignore
  models/
    model.axmodel      # 已编译的 AXMODEL
    model_meta.json    # 模型元信息
  python/
    README.md          # Python SDK 使用说明（环境安装、运行、API）
    requirements.txt
    <model>_sdk/
  cpp/
    README.md          # C++ SDK 构建说明（本地/交叉编译、上板运行、API）
    CMakeLists.txt
    toolchain-aarch64.cmake
    include/
    src/
    examples/
  model_convert/
    README.md          # 从零复现的完整说明（环境、导出、校准、编译、产物检查）
    requirements.txt   # 复现所需 Python 依赖
    export_onnx.py     # ONNX 导出脚本
    model.onnx
    model_meta.json
    pulsar2_config.json
    compile_pulsar2.sh # 可直接执行的编译脚本
    calib_data.tar     # 校准数据（或 README 中说明如何生成）
  reports/
    performance_report.md
```



## 进度报告规则

每个阶段执行时，向用户报告以下信息：

1. **阶段开始**：阶段名称、预计耗时（如 ACQUIRE: 预计 2-5 分钟）。
2. **进行中**：关键操作的进度（下载百分比、编译步骤、测试结果数）。
3. **阶段完成**：产物路径、关键指标（文件大小、精度、耗时）、是否通过验证。
4. **下一阶段预告**：即将执行什么、是否需要用户输入。

进度格式示例：

```
[2/9] EXPORT — 导出 ONNX 并验证
  ✓ ONNX 导出完成 (12 MB, opset=17)
  ✓ ONNX Runtime 加载通过
  ✓ 原模型 vs ONNX cosine=0.9998
  → 下一阶段: TOOLCHAIN (准备 Pulsar2 编译环境, 预计 5-10 分钟)
```
## 强制记录

每个阶段都要更新：

- `TASK_DIR/task.md`: 阶段状态、命令摘要、产物路径、验证结果。
- `TASK_DIR/analysis.md`: 技术判断、失败原因、修复方案、配置取舍。

所有中间文件必须位于 `TASK_DIR`，不得修改原始模型来源。已解决的通用问题记录到仓库根目录 `issues/`。

**凭据脱敏**：`task.md` 和 `analysis.md` 中不得明文记录 `BOARD_PASSWORD`、`HF_TOKEN` 等凭据。如必须引用，使用 `***` 替代。

## 环境与下载约束

- 遇到 HuggingFace repo、模型权重或 Pulsar2 fallback 下载时，必须使用 `hf-mirror`，优先设置 `HF_ENDPOINT=https://hf-mirror.com`，并把实际下载端点记录到 `task.md`。
- Python 虚拟环境统一使用 `uv` 管理：创建环境用 `uv venv`，安装依赖用 `uv pip install --python <venv>/bin/python ...`，不得使用 `python -m venv`、`virtualenv` 或 `conda` 创建任务环境。
- 如本机缺少 `uv`，先给出安装命令并 STOP：

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或通过 pip
pip install uv
```

若用户环境无法安装 uv（如离线环境、受限权限），记录到 `analysis.md` 并 STOP，等待用户提供替代方案。

## 阶段调度

- `ACQUIRE`: 读取 [hidden/acquire/SKILL.md](hidden/acquire/SKILL.md)。
- `INIT`: 读取 [hidden/init/SKILL.md](hidden/init/SKILL.md)。
- `EXPORT`: 读取 [hidden/export/SKILL.md](hidden/export/SKILL.md)。
- `TOOLCHAIN`: 读取 [hidden/toolchain/SKILL.md](hidden/toolchain/SKILL.md)。
- `COMPILE`: 读取 [hidden/compile/SKILL.md](hidden/compile/SKILL.md)。
- `SIMULATE`: 读取 [hidden/simulate/SKILL.md](hidden/simulate/SKILL.md)。
- `SDK-GEN`: 读取 [hidden/sdk-gen/SKILL.md](hidden/sdk-gen/SKILL.md)。
- `RUNONBOARD`: 读取 [hidden/runonboard/SKILL.md](hidden/runonboard/SKILL.md)。
- `PACKAGE`: 读取 [hidden/package/SKILL.md](hidden/package/SKILL.md)。该阶段必须以"客户从零开始看 GitHub 仓库"的视角生成 package/，完成后自动上板按 README 从零搭建环境、编译、运行，发现任何卡点立即修正，直到客户能无阻碍复现为止。

## STOP 点

必须 STOP 的情况：

- `SOURCE`、`TARGET_HARDWARE` 缺失（入口即检查，防止无效执行）。
- 主模型文件或导出入口无法自动判断。
- 只能使用随机校准数据，且用户未确认。
- ONNX 与原模型对分失败。
- ONNX 存在动态 shape，且静态化失败（Pulsar2 不接受动态 ONNX）。
- Pulsar2 缺失，且无法从本地路径、用户提供镜像或 HuggingFace `AXERA-TECH/Pulsar2` 镜像运行。
- 编译失败需要修改模型图或改导出策略。
- SIMULATE 精度不达标（先查 `issues/` 目录，无匹配方案再 STOP）。

   仿真阶段除了 ONNX vs AXMODEL 对比外，还应执行原模型（如 PyTorch）vs AXMODEL 的端到端对比，使用相同输入、相同后处理逻辑，报告任务级指标（如分类准确率、检测 mAP），让客户直观了解从浮点模型到芯片模型的精度损失。
- 需要私有模型凭据、板端凭据或其他敏感输入。

BOARD 缺失不是 STOP 条件——工作流自动跳过 RUNONBOARD 阶段继续执行。


## 接受标准

- `export/model.onnx` 为静态 shape，并可被 `onnxruntime` 加载。
- `export/model_meta.json` 含完整输入输出名称、shape、dtype、layout。
- `compile/model.axmodel` 存在。
- `simulate/simulate_report.md` 给出 ONNX vs AXMODEL 指标，默认 `cosine >= 0.99` 或任务语义等价。
- Python SDK import 成功；上板验证时必须使用 `pyaxengine`/`AxEngineExecutionProvider` 真实运行。
- C++ SDK 至少 `cmake configure` 成功；存在 BSP（含交叉编译器和 AX runtime）时完成交叉编译，上板验证时必须链接 AX Engine runtime 真实运行。
- `ax_run_model` 只允许作为 AXMODEL smoke check，不能作为 Python/C++ SDK 的实现或验证替代。
- RUNONBOARD 阶段：若提供了 BOARD，必须执行板端验证并产出报告；若未提供 BOARD，自动跳过，交付包中相关数据标注 N/A。

- `package/` 满足客户从零复现的全部要求，并通过板端自验证：
  - `package/README.md` 详尽覆盖模型概述、快速开始（推理/复现两条路径）、目录说明、性能摘要、已知限制。
  - `package/model_convert/` 包含 `requirements.txt`、`export_onnx.py`、`compile_pulsar2.sh`、完整 pulsar2 配置和 README，客户可按步骤从 ONNX 导出到 AXMODEL 编译。
- 各阶段在需要引用 AX runtime 库时，统一使用 `AX_RUNTIME_TYPE` 决策，该变量由 TOOLCHAIN 阶段检测板端 runtime 后设置：
  - `axcl`: 板端有 `axcl_run_model` 时使用。链接 `libaxcl_rt.so` 等 AXCL 库，头文件在 `axcl/include/external/`。
  - `axengine`: 板端无 `axcl_run_model` 时使用。链接 `libax_engine.so`/`libax_sys.so`，使用 axengine API。
  - `package/model_convert/README.md` 覆盖环境准备（Python、Docker、Pulsar2）、ONNX 导出、校准数据、编译命令（完整无省略）、产物检查、常见问题。
  - `package/python/README.md` 覆盖环境安装、运行示例、API 说明。
  - `package/cpp/README.md` 覆盖本机构建、BSP 安装和交叉编译、上板运行、API 说明。
  - 所有 README 中的命令完整无省略，可直接复制执行，不依赖客户机器的预设路径。
  - `package/` 不包含原始私有凭据、缓存、虚拟环境、node_modules 或大型无关中间文件。

  - `package/` 已通过板端自验证：将整个 `package/` 目录推送到目标板端，严格按照 `package/README.md` 和 `model_convert/README.md` 的步骤从零安装环境、编译、运行推理，所有命令可无障碍执行，无遗漏依赖或错误路径。验证过程中发现的任何问题均在 `package/` 内就地修正并重新验证，直到 README 中所有步骤可连续无中断执行完毕。
- `package/reports/performance_report.md` 存在，含以下内容：
  - 流水线各阶段耗时与端到端总耗时。
  - 模型效率：ONNX 大小、AXMODEL 大小、压缩比、MACs、MACs 利用率。
  - 推理延迟：仿真延迟、板端 Python/C++ SDK 延迟。
  - 板端内存：系统内存增量、CMM 专用内存（若可获取则记录，否则 N/A）。
  - 精度汇总（多输入均值 ± 标准差）。
- 所有性能指标为记录性质，不设硬性通过阈值；获取失败时标记 N/A。
- `simulate/simulate_report.md` 的精度指标基于 ≥3 组输入样本，报告均值 ± 标准差，同时含仿真单次推理延迟。`simulate/simulate_report.md` 的精度指标基于 ≥3 组输入样本，报告均值 ± 标准差，同时含仿真单次推理延迟。
- 交付包中应包含模型版本追溯信息：SOURCE URL/commit hash、导出时间、Pulsar2 版本、AXMODEL 编译配置 hash。当上游模型更新时，可通过这些信息判断是否需要重新编译。
