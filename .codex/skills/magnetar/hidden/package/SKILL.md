---
name: package
description: Hidden stage for magnetar. Assemble validated AXMODEL, SDKs, reports, and usage documentation into a customer delivery directory.
---

# PACKAGE

目标：形成一份客户拿到后能从零复现模型转换并运行 Python/C++ SDK 的交付包。所有说明文档必须详尽到新人按步骤操作即可完成，包括环境安装、工具使用方法、每步预期产物。

## 分发策略：GitHub vs HuggingFace

PACKAGE 产物需同时推送 GitHub 和 HuggingFace，但内容不同：

### GitHub（源码 + 可复现）

| 目录 | 内容 |
|------|------|
| `models/` | model.axmodel + model_meta.json |
| `cpp/` | 源码 + CMakeLists.txt（FetchContent libdet.axera）+ toolchain-aarch64.cmake |
| `python/` | Python SDK 源码 |
| `model_convert/` | ONNX 导出脚本、Pulsar2 配置、校准数据、编译脚本 |
| `reports/` | 各阶段报告 |
| `demo/` | 测试图片 |

> GitHub 不含编译产物（bin/ lib/ include/），这些通过 GitHub Release 分发。

### HuggingFace（开箱即用）

| 目录 | 内容 |
|------|------|
| `models/` | model.axmodel + model_meta.json |
| `cpp/bin/` | visdrone_detect（预编译 aarch64） |
| `cpp/lib/` | libdet.so（预编译 aarch64） |
| `cpp/include/` | 头文件 |
| `python/` | Python SDK 源码 |
| `demo/` | 测试图片 |

> HF **不含** `model_convert/`、C++ 源码、CMake 文件、`reports/`。客户只关心使用，不关心转换。

### GitHub Release

预编译 aarch64 二进制通过 Release assets 发布：model.axmodel + libdet.so + visdrone_detect。

### HF README 格式

HF README 必须以 YAML frontmatter 开头，含 `language`、`license`、`tags`、`datasets`、`library_name`、`pipeline_tag`。

### README 策略

- GitHub 和 HF 均只保留顶层 `README.md`，删除 `cpp/README.md`、`python/README.md` 等子目录 README

## 步骤

1. 清空并重建 `package/`。
2. 复制：
   - `compile/model.axmodel` -> `package/models/model.axmodel`
   - `export/model_meta.json` -> `package/models/model_meta.json`
   - `sdk/python/` -> `package/python/`
   - `sdk/cpp/` -> `package/cpp/`
   - ONNX 导出脚本、ONNX 产物、Pulsar2 配置、编译命令说明 -> `package/model_convert/`
   - 阶段报告 -> `package/reports/`
3. **YOLO 模型额外步骤**：若当前模型为 YOLO 系列（按 sdk-gen 阶段判定规则），执行以下操作：
   - 确保 `package/python/<model>_sdk/` 已包含 `pydet/` 子目录（从 sdk-gen 阶段复制）
   - 确保 `package/cpp/CMakeLists.txt` 已包含 libdet.axera 的 FetchContent 或 add_subdirectory 集成
   - 在 `package/README.md` 中增加 libdet.axera 的获取和编译说明
4. 生成 `package/reports/performance_report.md`，汇总所有阶段采集的性能数据。从各阶段报告中提取：
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
5. 生成 `package/README.md`（详见下方 [顶层 README.md](#顶层-readmemd)）。
6. 生成项目级辅助文件：
   - `.gitignore`: 忽略 Python 缓存、CMake build、临时输出文件。
   - `manifest.json`（必须）：列出交付包中每个文件的 SHA256 哈希、文件大小（字节）、最后修改时间。格式：

```json
{
  "package_version": "1.0",
  "generated_at": "2026-07-20T12:00:00Z",
  "model_name": "yolov8n",
  "target_hardware": "AX650",
  "pulsar2_version": "6.0",
  "files": [
    {"path": "models/model.axmodel", "sha256": "abc123...", "size_bytes": 4123456},
    {"path": "models/model_meta.json", "sha256": "def456...", "size_bytes": 1234}
  ]
}
```

客户可通过 `sha256sum -c <(jq -r '.files[] | "\(.sha256)  \(.path)"' manifest.json)` 验证交付包完整性。

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
    <model>_sdk/
      __init__.py
      inference.py
      preprocess.py
      postprocess.py
      pydet/            # YOLO 模型专属：libdet.axera Python 绑定
        __init__.py
        pydet.py
        pyaxdev.py
  cpp/
    README.md          # C++ SDK 使用说明（含 API 和运行方法）
    bin/
      visdrone_detect  # 预编译 aarch64 可执行程序（开箱即用）
    include/
      libdet.h         # C API 头文件
      ax_devices.h     # 设备枚举头文件
    lib/
      libdet.so        # 预编译 aarch64 共享库（OpenCV 静态链接）
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
  - **YOLO 模型额外依赖**：
    - Python: 编译 `libdet.so`（从 https://github.com/AXERA-TECH/libdet.axera.git 获取源码，`./build.sh` 编译，将 `libdet.so` 放入 LD_LIBRARY_PATH）
    - C++: `libopencv-dev`，libdet.axera 源码编译
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
   ```
   若 `pyaxengine` 需要从源码安装，给出完整的 `git clone` + `pip install` 命令。
   **YOLO 模型额外步骤**：
   ```
   git clone https://github.com/AXERA-TECH/libdet.axera.git
   cd libdet.axera && ./build.sh
   export LD_LIBRARY_PATH=$(pwd)/build/lib:${LD_LIBRARY_PATH}
   ```
3. **快速运行**：完整命令行示例，含输入文件格式要求。
4. **API 说明**：SDK 类的初始化参数、推理方法签名、返回值结构。
5. **输入预处理说明**：resize 策略、归一化参数、颜色通道顺序。

---

## C++ SDK README.md

`package/cpp/README.md` 必须包含：

1. **文件说明**：列出 bin/、lib/、include/ 目录的文件和用途。
2. **运行依赖**：列出板端运行时库（`/soc/lib/libax_engine.so`、`/soc/lib/libax_sys.so`）。
3. **用法**：
   - 直接运行预编译程序：完整的命令行示例。
   - 集成到自己的项目：包含 `#include "libdet.h"`、API 调用示例、编译命令。
4. **编译（如需）**：指向 GitHub 仓库源码链接和交叉编译依赖。
   - 交叉编译器 + BSP SDK 版本说明。
5. **API 说明**：`ax_det_init_t` 结构体字段、`ax_det()/ax_det_init()/ax_det_deinit()` 函数签名。

---

## model_convert 要求

目标：客户拿到 `model_convert/` 后，只需安装 Python 依赖 + Pulsar2 环境即可从零复现 ONNX 导出到 AXMODEL 编译的完整流程。


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


### compile_pulsar2.sh

必须是一份可直接执行的完整编译脚本，包含：
- Pulsar2 镜像检查（`docker images | grep pulsar2`），不存在时提示从 HuggingFace 下载并 `docker load`。
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
  ```
- **Pulsar2 环境**：
  - 从 HuggingFace 下载 Docker 镜像 tar.gz（完整 URL，如 `https://hf-mirror.com/AXERA-TECH/Pulsar2/resolve/main/6.0/ax_pulsar2_6.0.tar.gz`）。
  - 用 `docker load < ax_pulsar2_6.0.tar.gz` 导入镜像。
  - Docker 运行方式说明（挂载目录等）。
- 验证环境：列出检查命令（`python --version`、`docker --version`、`docker images | grep pulsar2`、`pip list | grep onnx`）。

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
- 不得遗漏环境安装步骤（认为客户已装好所有工具）。

## 验证

- 所有 README 中的命令完整无省略、可直接复制执行。
- 环境安装说明覆盖 Python、Pulsar2（Docker）、芯片 BSP/交叉编译工具链。
- `package/reports/performance_report.md` 存在且各节内容完整（缺失数据标 N/A）。
- `package/` 可作为项目根目录阅读和构建，客户不需要理解 `TASK_DIR` 内部结构。
- README 不依赖内部临时路径才能理解。
- `package/` 中不包含原始私有凭据、缓存、虚拟环境、node_modules 或大型无关中间文件。
- **YOLO 模型额外检查**：
  - `package/python/<model>_sdk/pydet/` 目录存在且包含 `pydet.py`、`pyaxdev.py`、`__init__.py`
  - `package/cpp/CMakeLists.txt` 包含 libdet.axera 的 FetchContent 或 add_subdirectory 集成
  - `package/README.md` 和 `package/python/README.md` 中包含 libdet.axera 克隆和编译步骤
  - `package/cpp/README.md` 中包含 libdet.axera 依赖说明和 OpenCV 安装步骤

## 板端自验证

生成 `package/` 后，必须以"客户从零开始看 GitHub 仓库"的视角，将整个交付包部署到目标板端并严格按 README 步骤执行。这是 PACKAGE 阶段不可跳过的核心环节，目的是确保客户拿到包后能无障碍复现。

### 原则

- **以 README 为准**：严格按 `package/README.md`、`package/model_convert/README.md`、`package/python/README.md`、`package/cpp/README.md` 中的命令执行，不依赖 TASK_DIR 内部路径或预设环境。
- **在板端做验证**：将 `package/` 完整推送到板端，不依赖主机临时代理。
- **即时修正**：发现任何 README 命令不可执行、脚本报错、依赖缺失、路径错误等问题，立即在 `package/` 内就地修正，并重新验证，直到所有步骤可连续无中断执行。
- **修正范围**：只修改 `package/` 内的 README、脚本和配置文件，不动 TASK_DIR 其他阶段产物。

### 步骤

#### 1. 推送 package/ 到板端

使用 `scp -r` 或等效方式将整个 `package/` 目录推送到板端用户可写的位置：

```bash
sshpass -p '<BOARD_PASSWORD>' scp -r -o StrictHostKeyChecking=no \
  package/ <BOARD_USER>@<BOARD_IP>:~/magnetar-package/
```

记录推送结果到 `task.md`。

#### 2. 按 README 路径 A 验证：直接用 AXMODEL 推理

严格按照 `package/README.md` 中"路径 A：直接用已编译的 AXMODEL 推理"的步骤：

1. **Python 环境安装**：按 `package/python/README.md` 从零安装 Python 依赖（pip install、pyaxengine 安装等），记录每个命令的退出码和输出。
   - **YOLO 模型**：额外执行 libdet.axera 克隆和编译步骤，验证 `libdet.so` 生成且可被 Python ctypes 加载。
2. **Python 推理**：按 README 中的示例命令运行 Python 推理，验证输出格式和结果。
3. **C++ 构建**（若 SDK_LANG 含 cpp）：
   - 按 `package/cpp/README.md` 在主机完成交叉编译（cmake configure + make）。
   - **YOLO 模型**：确认 CMake 成功拉取或找到 libdet.axera 源码并完成链接。
   - 将编译产物推送到板端。
   - 按 README 中的运行命令执行 C++ 推理。
4. **结果验证**：对比 Python/C++ 输出与预期值（shape、dtype、cosine、MAE），记录到 `analysis.md`。

#### 3. 按 README 路径 B 验证：从零复现模型转换

严格按照 `package/model_convert/README.md` 的步骤：

1. **环境准备**：按 README 安装 Python 依赖（`pip install -r requirements.txt`），检查 Docker/Pulsar2 环境。
2. **ONNX 导出**：执行 `python export_onnx.py ...`，验证产出 `model.onnx`。
3. **Pulsar2 编译**：执行 `./compile_pulsar2.sh` 或 README 中的完整 `pulsar2 build` 命令，验证产出 `model.axmodel`。
4. **产物检查**：按 README 中的产物检查表确认文件存在且大小合理。

#### 4. 问题发现与即时修正

每遇到一个步骤失败，执行以下循环：

1. **诊断**：分析失败原因（依赖缺失、路径错误、权限问题、配置不对等），记录到 `analysis.md`。
2. **修正**：在 `package/` 内就地修正：
   - README 命令错误 → 修正命令
   - 依赖缺失 → 补充 `requirements.txt`
   - 路径不对 → 修正 README 或脚本中的路径
   - 配置错误 → 修正 `pulsar2_config.json` 或 `CMakeLists.txt`
   - 脚本 bug → 修正脚本
3. **重试**：重新执行当前步骤和后续步骤。
4. **记录**：每次修正后更新 `task.md`，描述问题、根因、修正内容、重试结果。

#### 5. 最终验证清单

板端自验证通过后，确认以下清单全部满足：

- [ ] `package/README.md` 路径 A 所有命令可无障碍执行，Python 推理输出正确
- [ ] `package/README.md` 路径 A 的 C++ 构建和运行命令可无障碍执行（若 SDK_LANG 含 cpp）
- [ ] `package/model_convert/README.md` 所有命令可无障碍执行，从零完成 ONNX 导出和 AXMODEL 编译
- [ ] 所有 README 中无占位符、无省略号、无 `<path>` 等未填内容
- [ ] 所有 `requirements.txt` 完整覆盖所需依赖
- [ ] `compile_pulsar2.sh` 可直接执行，无变量间接引用
- [ ] `package/` 内无私有凭据、缓存、虚拟环境、中间文件
- [ ] **YOLO 模型额外检查**：`libdet.so` 成功编译并可被 SDK 加载，推理后处理输出正确的检测框/关键点

### 与 RUNONBOARD 的关系

- `RUNONBOARD` 阶段验证模型在板端的功能正确性和性能（精度、延迟、内存），使用的是 TASK_DIR 内的 SDK 示例。
- `PACKAGE` 板端自验证验证的是交付包的可复现性和文档完备性，以"客户视角"执行 README。
- 两者互补：RUNONBOARD 确保模型能跑，PACKAGE 板端自验证确保客户能独立跑通。

### STOP

- 板端自验证发现的问题修正后仍反复失败超过 3 轮，STOP 并报告未解决的问题和根因分析。
- 板端缺少必要运行时（如 `pyaxengine`、AX runtime 库）且无法自动安装，STOP 并说明缺失项。
- **YOLO 模型**：若板端无法编译 libdet.axera（缺少 OpenCV 或其他依赖），STOP 并说明缺失项和安装方法建议。
