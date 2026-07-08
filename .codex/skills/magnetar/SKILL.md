---
name: magnetar
description: Convert remote or local AI models into AXera AXMODEL packages with Python and C++ SDKs for customer delivery. Use when Codex must acquire a model from Git/HuggingFace/URL/local path, export ONNX, compile with Pulsar2, simulate/validate AXMODEL accuracy, optionally run on AX hardware, generate SDKs, or package deployment artifacts.
---

# Magnetar

始终用中文沟通。该 skill 是 Magnetar 的公开入口，用于把远程或本地模型转换为客户可用的 AXMODEL 交付包。

严格按以下顺序推进：

## 阶段不可跳过

所有 9 个阶段必须全部遍历，不可跳过。即使用户直接提供了 ONNX 模型文件，ACQUIRE 和 EXPORT 阶段同样必须执行，按各阶段的产物和验证要求完成全量检查：

- ACQUIRE 必须产出来源记录和候选文件清单，即使 SOURCE 是单个 ONNX 文件。
- EXPORT 必须完成 ONNX checker、ONNX Runtime 加载、model_meta.json、校准数据和导出报告，即使模型本身已经是 ONNX 格式。
- 跳过任一阶段会导致后续产物缺失（如 manifest.json、model_meta.json、校准数据），最终 PACKAGE 交付包将不满足客户从零复现的要求。


`ACQUIRE -> INIT -> EXPORT -> TOOLCHAIN -> COMPILE -> SIMULATE -> SDK-GEN -> RUNONBOARD -> PACKAGE`

`RUNONBOARD` 必须执行。`BOARD` 在工作流入口即检查，缺失时立即 STOP，不会先执行前置阶段。遇到 `STOP` 必须暂停等待用户确认。

机器可读规范见 [../../workflows/magnetar.yaml](../../workflows/magnetar.yaml)。

## 输入

- `SOURCE`: 必填。Git 仓库、HuggingFace repo、本地目录、单模型文件或可下载 URL。
- `TARGET_HARDWARE`: 必填。默认支持 `AX650`、`AX620E`，其他 AX 芯片需确认 Pulsar2 支持。
- `MODEL_NAME`: 可选。默认从 `SOURCE` 推断。
- `TASK_DIR`: 可选。默认 `todos/work/<timestamp>-<model-name>/`。
- `SDK_LANG`: 可选。`python`、`cpp`、`both`，默认 `both`。
- `HF_TOKEN`: 条件必填。私有 HuggingFace 模型从环境变量读取。
- `BOARD`: 必填。板端 SSH 信息，格式优先为 `user@host[:port]`。入口即检查，缺失时 STOP。
- `BOARD_PASSWORD`: 必填。用户已确认的默认板端密码为 `123456`。
- `PULSAR2_IMAGE` 或 `PULSAR2_BIN`: 可选。Pulsar2 Docker 镜像或本地可执行文件；本地没有 Pulsar2 时，默认从 `https://hf-mirror.co/AXERA-TECH/Pulsar2/tree/main` 获取 Docker 镜像。
- `CXX_BSP_URL`: 可选。C++ BSP SDK 下载地址，含交叉编译器和 AX runtime。默认按目标芯片选择：
  - AX650: `https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub/resolve/main/sdk/edge-computing-AX650_SDK_V3.10.2/02.%20SDK/AX650_SDK_V3.10.2/AX650_SDK_V3.10.2_20260513151335.tgz`
  - AX620E: `https://developer.arm.com/-/media/Files/downloads/gnu-a/9.2-2019.12/binrel/gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz`（待更新为BSP）

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

## 强制记录

每个阶段都要更新：

- `TASK_DIR/task.md`: 阶段状态、命令摘要、产物路径、验证结果。
- `TASK_DIR/analysis.md`: 技术判断、失败原因、修复方案、配置取舍。

所有中间文件必须位于 `TASK_DIR`，不得修改原始模型来源。已解决的通用问题记录到仓库根目录 `issues/`。

## 环境与下载约束

- 遇到 HuggingFace repo、模型权重或 Pulsar2 fallback 下载时，必须使用 `hf-mirror`，优先设置 `HF_ENDPOINT=https://hf-mirror.co`，并把实际下载端点记录到 `task.md`。
- Python 虚拟环境统一使用 `uv` 管理：创建环境用 `uv venv`，安装依赖用 `uv pip install --python <venv>/bin/python ...`，不得使用 `python -m venv`、`virtualenv` 或 `conda` 创建任务环境。
- 如本机缺少 `uv`，STOP 并要求用户安装或提供可用的 `uv` 路径；不要降级为其他虚拟环境管理器。

## 阶段调度

- `ACQUIRE`: 读取 [hidden/acquire/SKILL.md](hidden/acquire/SKILL.md)。
- `INIT`: 读取 [hidden/init/SKILL.md](hidden/init/SKILL.md)。
- `EXPORT`: 读取 [hidden/export/SKILL.md](hidden/export/SKILL.md)。
- `TOOLCHAIN`: 读取 [hidden/toolchain/SKILL.md](hidden/toolchain/SKILL.md)。
- `COMPILE`: 读取 [hidden/compile/SKILL.md](hidden/compile/SKILL.md)。
- `SIMULATE`: 读取 [hidden/simulate/SKILL.md](hidden/simulate/SKILL.md)。
- `SDK-GEN`: 读取 [hidden/sdk-gen/SKILL.md](hidden/sdk-gen/SKILL.md)。
- `RUNONBOARD`: 读取 [hidden/runonboard/SKILL.md](hidden/runonboard/SKILL.md)。
- `PACKAGE`: 读取 [hidden/package/SKILL.md](hidden/package/SKILL.md)。

## STOP 点

必须 STOP 的情况：

- `SOURCE`、`TARGET_HARDWARE` 或 `BOARD` 缺失（入口即检查，防止无效执行）。
- 主模型文件或导出入口无法自动判断。
- 只能使用随机校准数据，且用户未确认。
- ONNX 与原模型对分失败。
- ONNX 存在动态 shape，且静态化失败（Pulsar2 不接受动态 ONNX）。
- Pulsar2 缺失，且无法从本地路径、用户提供镜像或 HuggingFace `AXERA-TECH/Pulsar2` 镜像运行。
- 编译失败需要修改模型图或改导出策略。
- SIMULATE 精度不达标（先查 `issues/` 目录，无匹配方案再 STOP）。
- 需要私有模型凭据、板端凭据或其他敏感输入。


## 接受标准

- `export/model.onnx` 为静态 shape，并可被 `onnxruntime` 加载。
- `export/model_meta.json` 含完整输入输出名称、shape、dtype、layout。
- `compile/model.axmodel` 存在。
- `simulate/simulate_report.md` 给出 ONNX vs AXMODEL 指标，默认 `cosine >= 0.99` 或任务语义等价。
- Python SDK import 成功；上板验证时必须使用 `pyaxengine`/`AxEngineExecutionProvider` 真实运行。
- C++ SDK 至少 `cmake configure` 成功；存在 BSP（含交叉编译器和 AX runtime）时完成交叉编译，上板验证时必须链接 AX Engine runtime 真实运行。
- `ax_run_model` 只允许作为 AXMODEL smoke check，不能作为 Python/C++ SDK 的实现或验证替代。

- `package/` 满足客户从零复现的全部要求：
  - `package/README.md` 详尽覆盖模型概述、快速开始（推理/复现两条路径）、目录说明、性能摘要、已知限制。
  - `package/model_convert/` 包含 `requirements.txt`、`export_onnx.py`、`compile_pulsar2.sh`、完整 pulsar2 配置和 README，客户可按步骤从 ONNX 导出到 AXMODEL 编译。
  - `package/model_convert/README.md` 覆盖环境准备（Python、Docker、Pulsar2）、ONNX 导出、校准数据、编译命令（完整无省略）、产物检查、常见问题。
  - `package/python/README.md` 覆盖环境安装、运行示例、API 说明。
  - `package/cpp/README.md` 覆盖本机构建、BSP 安装和交叉编译、上板运行、API 说明。
  - 所有 README 中的命令完整无省略，可直接复制执行，不依赖客户机器的预设路径。
  - `package/` 不包含原始私有凭据、缓存、虚拟环境、node_modules 或大型无关中间文件。

- `package/reports/performance_report.md` 存在，含以下内容：
  - 流水线各阶段耗时与端到端总耗时。
  - 模型效率：ONNX 大小、AXMODEL 大小、压缩比、MACs、MACs 利用率。
  - 推理延迟：仿真延迟、板端 Python/C++ SDK 延迟。
  - 板端内存：系统内存增量、CMM 专用内存（若可获取则记录，否则 N/A）。
  - 精度汇总（多输入均值 ± 标准差）。
- 所有性能指标为记录性质，不设硬性通过阈值；获取失败时标记 N/A。
- `simulate/simulate_report.md` 的精度指标基于 ≥3 组输入样本，报告均值 ± 标准差，同时含仿真单次推理延迟。
