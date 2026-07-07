---
name: package
description: Hidden stage for magnetar. Assemble validated AXMODEL, SDKs, reports, and usage documentation into a customer delivery directory.
---

# PACKAGE

目标：形成一份客户拿到后能从零复现模型转换并运行 Python/C++ SDK 的交付包。所有说明文档必须详尽到新人按步骤操作即可完成，包括环境安装、工具使用方法、每步预期产物。

## 步骤

1. 清空并重建 `package/`。
2. 复制：
   - `compile/model.axmodel` -> `package/models/model.axmodel`
   - `export/model_meta.json` -> `package/models/model_meta.json`
   - `sdk/python/` -> `package/python/`
   - `sdk/cpp/` -> `package/cpp/`
   - ONNX 导出脚本、ONNX 产物、Pulsar2 配置、编译命令说明 -> `package/model_convert/`
   - 阶段报告 -> `package/reports/`
3. 生成 `package/reports/performance_report.md`，汇总所有阶段采集的性能数据。从各阶段报告中提取：
   - **流水线耗时**：从 `task.md` 提取各阶段耗时，计算端到端总耗时。
   - **模型效率**：从 `compile_report.md` 提取 ONNX 大小、AXMODEL 大小、压缩比、MACs。若已知芯片理论算力，计算 MACs 利用率。
   - **推理延迟**：从 `simulate_report.md` 提取仿真延迟；从 `runonboard_report.md` 提取板端 Python/C++ 延迟。
   - **板端内存**：从 `runonboard_report.md` 提取系统内存增量和 CMM 占用（若已采集）。
   - **精度汇总**：从 `simulate_report.md` 提取多输入指标均值 ± 标准差。

   格式参考：
   ```markdown
   # Performance Report

   ## 流水线耗时
   | 阶段 | 耗时(s) |
   |------|---------|
   | ACQUIRE | X |
   | INIT | X |
   | EXPORT | X |
   | TOOLCHAIN | X |
   | COMPILE | X |
   | SIMULATE | X |
   | SDK-GEN | X |
   | RUNONBOARD | X（或 skipped） |
   | PACKAGE | X |
   | **总计** | X |

   ## 模型效率
   - ONNX 大小: X MB
   - AXMODEL 大小: X MB
   - 压缩比: X:1
   - MACs: X G
   - MACs 利用率: X%（若可计算）

   ## 推理延迟
   - 仿真 (pulsar2 run): X ms
   - 板端 Python SDK: X ms（或 N/A）
   - 板端 C++ SDK: X ms（或 N/A）

   ## 板端内存
   - 系统内存增量: X MB（或 N/A）
   - CMM 占用: X MB（或 N/A）

   ## 精度汇总（多输入，均值 ± 标准差）
   | 指标 | 值 |
   |------|-----|
   | cosine | 0.XXX ± 0.00X |
   | MAE | X.XXX ± X.XXX |
   | max abs diff | X.XXX ± X.XXX |
   ```
4. 生成 `package/README.md`（详见下方 [顶层 README.md](#顶层-readmemd)）。
5. 生成项目级辅助文件：
   - `.gitignore`: 忽略 Python 缓存、CMake build、临时输出文件。
   - 可选 `manifest.json`: 列出文件 SHA256、版本、时间戳。

## 目录结构

```text
package/
  README.md
  .gitignore
  models/
    model.axmodel      # 编译产物 AXMODEL
    model_meta.json    # 模型元信息（输入/输出 tensor 定义）
  python/
    README.md          # Python SDK 使用说明（含环境安装、API 文档）
    requirements.txt
    <model>_sdk/
      __init__.py
      inference.py
      preprocess.py
      postprocess.py
      example.py
      requirements.txt
  cpp/
    README.md          # C++ SDK 构建说明（含本地/交叉编译、运行方法）
    CMakeLists.txt
    toolchain-aarch64.cmake
    include/
    src/
    examples/
  model_convert/
    README.md          # 从零复现模型转换的完整说明
    requirements.txt   # 复现所需的 Python 依赖
    export_onnx.py     # ONNX 导出脚本（从原始模型工程复制）
    model.onnx         # 导出的 ONNX 模型
    model_meta.json    # 模型元信息（与 models/ 中的一致）
    pulsar2_config.json
    compile_pulsar2.sh # 完整编译命令脚本（可直接执行）
    calib_data.tar     # 校准数据集（或 README 中说明如何生成）
  reports/
    performance_report.md
```

## 顶层 README.md

`package/README.md` 是客户拿到包后的第一个入口，必须详尽覆盖以下内容：

### 1. 模型概述
- 模型名称、任务类型（分类/检测/分割/LLM 等）、目标芯片型号。
- 输入规格：shape、dtype、layout（NCHW/NHWC）、数值范围（[0,1] 或 [0,255]）、预处理方式（mean/std、resize 等）。
- 输出规格：每个输出 tensor 的名称、shape、dtype、含义。
- 类别列表（如适用）。

### 2. 目录说明
- 逐目录说明用途，让客户知道每个文件夹做什么。

### 3. 快速开始
分两条路径，分别指导运行已编译好的模型和从头复现模型转换：

**路径 A：直接用已编译的 AXMODEL 推理**
- 环境安装：
  - Python SDK：安装 `pyaxengine` 的方法（pip 安装或源码安装，给出完整 URL）。
  - C++ SDK：列出编译器、CMake、AX runtime 的获取和安装步骤。
- 运行示例：
  - Python：完整的 `pip install -r requirements.txt` + `python example.py <image>` 命令。
  - C++：完整的 `mkdir build && cd build && cmake .. && make` 和运行命令。

**路径 B：从零复现模型转换**
- 链接到 `model_convert/README.md`，概要说明需要安装的依赖和大致步骤。

### 4. 性能摘要
引用 `reports/performance_report.md`，列出关键指标：推理延迟、精度、模型大小。

### 5. 已知限制
- 输入分辨率、batch size 限制。
- 已知精度问题或边界 case。
- 芯片兼容性说明。

### 禁止项
- 不得使用占位符（`...`、`<path>`、`xxx`）。
- 所有命令必须可直接复制执行。
- 不得依赖客户机器上的预设路径或环境变量（除非明确说明如何设置）。

---

## Python SDK README.md

`package/python/README.md` 必须包含：

1. **环境要求**：Python 版本、系统依赖（如 libgl1）。
2. **安装步骤**：
   ```
   pip install -r requirements.txt
   pip install -r <model>_sdk/requirements.txt
   ```
   若 `pyaxengine` 需要从源码安装，给出完整的 `git clone` + `pip install` 命令。
3. **快速运行**：完整命令行示例，含输入文件格式要求。
4. **API 说明**：SDK 类的初始化参数、推理方法签名、返回值结构。
5. **输入预处理说明**：resize 策略、归一化参数、颜色通道顺序。

---

## C++ SDK README.md

`package/cpp/README.md` 必须包含：

1. **环境要求**：
   - 本机构建：CMake 版本、C++ 编译器（gcc/clang）。
   - 交叉编译：芯片对应 BSP SDK 的下载地址和安装方法，给出完整 URL。（AX650: AX650 BSP SDK V3.10.2，AX620E: Arm GNU 工具链）。
   - AX runtime：头文件和库文件的获取路径，说明如何设置 `AX_RUNTIME_ROOT`。
2. **构建步骤**：
   - 本机构建（仅验证编译，不能运行推理）：
     ```
     mkdir build && cd build
     cmake .. -DCMAKE_BUILD_TYPE=Release
     make -j$(nproc)
     ```
   - 交叉编译（产物可上板运行，需先安装 BSP/工具链）：
     ```
     mkdir build_arm && cd build_arm
     cmake .. -DCMAKE_TOOLCHAIN_FILE=../toolchain-aarch64.cmake -DCMAKE_BUILD_TYPE=Release
     make -j$(nproc)
     ```
3. **上板运行**：如何将编译产物传到板端、设置 `LD_LIBRARY_PATH`、运行示例。
4. **API 说明**：类的构造、初始化、推理方法、输入输出数据格式。

---

## model_convert 要求

目标：客户拿到 `model_convert/` 后，只需安装 Python 依赖 + Pulsar2 环境即可从零复现 ONNX 导出到 AXMODEL 编译的完整流程。

### requirements.txt

必须包含从零复现所需的所有 Python 包，按类别分组注释。不能省略任何依赖：

```text
# ONNX 导出依赖
ultralytics          # 或其他模型框架（torch、transformers 等）
onnx
onnx-simplifier

# Pulsar2 编译依赖
# pulsar2 通过 Docker 提供，镜像地址见 README
# pulsar2镜像: https://hf-mirror.com/AXERA-TECH/Pulsar2

# 校准数据生成（如需要）
numpy
Pillow
```

若某依赖无 pip 包（如 Pulsar2 只能通过 Docker 使用），在 requirements.txt 中以注释形式给出获取方式，并在 README 中详细说明环境搭建步骤。

### compile_pulsar2.sh

必须是一份可直接执行的完整编译脚本，包含：
- Pulsar2 环境激活（如 `source /path/to/pulsar2_env/bin/activate`）或 Docker run 命令。
- 完整的 `pulsar2 build` 命令及其所有参数。不得使用变量间接引用（除非在脚本开头明确赋值）。
- 产物路径说明（编译后输出到哪个目录）。
- 异常处理：编译失败时的诊断建议（如检查磁盘空间、Docker 是否运行）。

### 导出脚本

- 必须随包提供完整可运行的 `export_onnx.py`，从原始模型权重导出 ONNX。
- 脚本头部注释说明依赖、输入权重路径、输出路径、静态 shape 和算子版本。
- 必须包含实际使用的 Pulsar2 配置文件，明确 `target_hardware`、输入 shape、dtype、layout、mean/std、calibration 设置。
- 必须保留或说明校准数据来源；如不随包提供校准数据，应在 README 写明如何重新生成。
- 不得开启 `"highest_mix_precision": true`。

### README.md

`model_convert/README.md` 必须是客户从零复现的唯一依赖文档，详尽到每步可执行的命令和预期输出。必须包含以下章节：

#### 1. 概述
- 一句话说明本文档做什么（从 ONNX 导出到 AXMODEL 编译）。
- 目标芯片和输入规格（从 `pulsar2_config.json` 提取）。
- 前置条件清单（Python 版本、磁盘空间、Docker）。

#### 2. 环境准备
- **Python 环境**：
  ```
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- **Pulsar2 环境**：
  - Docker 镜像地址（完整 URL，含 tag）。
  - Docker pull 命令。
  - Docker 运行方式说明（挂载目录、端口等）。
  - 若不用 Docker，说明本地安装步骤。
- 验证环境：列出检查命令（`python --version`、`docker --version`、`pip list | grep onnx`）。

#### 3. ONNX 导出（标题含具体模型名，如 YOLOv8-seg）
- 说明输入权重文件是什么、从哪里获取。
- 完整的导出命令：
  ```
  python export_onnx.py --weights <path-to-pt> --output model.onnx
  ```
- 验证导出产物：`ls -lh model.onnx`、`python -c "import onnx; onnx.checker.check_model('model.onnx'); print('OK')"`。

#### 4. 校准数据准备
- 校准数据的作用（量化校准）和格式要求（图片格式、分辨率、数量）。
- 如何生成 `calib_data.tar`：
  ```
  tar cf calib_data.tar /path/to/calib/images/*.png
  ```
- 若校准数据已随包提供，说明可直接使用。

#### 5. Pulsar2 编译
- 完整的编译命令，所有参数展示无省略：
  ```
  ./compile_pulsar2.sh
  ```
  或直接给出完整的 pulsar2 build 命令行（如果不用脚本）。
- 说明关键配置项含义：`target_hardware`、`input_shapes`、`calibration_mean/std`、`output_data_type`。
- 预期编译时间和产物：`./compile/model.axmodel`。

#### 6. 产物检查
| 文件 | 用途 | 预期大小 |
|------|------|----------|
| `model.onnx` | 导出的浮点模型 | ~X MB |
| `compile/model.axmodel` | 芯片可部署模型 | ~X MB |

#### 7. 常见问题
- 编译失败的可能原因及排查步骤（OOM、校准数据格式不对、Docker 未启动等）。

### 禁止项

- 不得在 README 或脚本中使用占位符或省略号（如 `...`、`--xxx`、`<path>`、`<fill me>`）。
- 不得省略 `pulsar2 build` 的完整参数列表。
- 不得遗漏校准数据来源说明。
- 不得遗漏 `requirements.txt`。
- 不得遗漏环境安装步骤（认为客户已装好所有工具）。

## 验证

- 必需文件齐全：`model_convert/requirements.txt`、`model_convert/compile_pulsar2.sh`、`model_convert/export_onnx.py`。
- 所有 README 中的命令完整无省略、可直接复制执行。
- 环境安装说明覆盖 Python、Pulsar2（Docker）、芯片 BSP/交叉编译工具链。
- `package/reports/performance_report.md` 存在且各节内容完整（缺失数据标 N/A）。
- `package/` 可作为项目根目录阅读和构建，客户不需要理解 `TASK_DIR` 内部结构。
- README 不依赖内部临时路径才能理解。
- `package/` 中不包含原始私有凭据、缓存、虚拟环境、node_modules 或大型无关中间文件。
