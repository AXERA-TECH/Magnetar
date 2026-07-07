---
name: sdk-gen
description: Hidden stage for magnetar. Generate customer-facing Python and C++ inference SDKs from model_meta.json and AXMODEL artifacts.
---

# SDK-GEN

目标：生成客户可直接集成的 Python/C++ SDK。SDK 自带的 README.md 必须详尽到客户无需查看其他文档即可安装环境、编译、运行示例。

## Python SDK

目录：`TASK_DIR/sdk/python/<model_name>_sdk/`

必须包含：

- `__init__.py`
- `inference.py`
- `preprocess.py`
- `postprocess.py`
- `example.py`
- `requirements.txt`
- `README.md`（详见下方 [Python SDK README.md](#python-sdk-readmemd)）

上级目录 `TASK_DIR/sdk/python/` 必须包含：
- `requirements.txt`（顶层依赖，如 pyaxengine）
- `README.md`（Python SDK 总览，含环境安装和快速运行）

实现要求：

- 必须使用 `pyaxengine` 的 `axengine.InferenceSession` 运行 AXMODEL。
- 默认 provider 必须显式设置为 `AxEngineExecutionProvider`；该 provider 不可用时，才允许按 `axengine.get_available_providers()` 选择 fallback provider，并在报告中记录。
- `requirements.txt` 必须说明 `pyaxengine` 来源：`https://github.com/AXERA-TECH/pyaxengine`。
- 从 `model_meta.json` 读取输入输出信息，不硬编码无法追溯的 shape。
- 必须提供可复用 SDK 类或等价封装，example 只负责实例化该类、加载输入、调用方法和展示结果。
- 示例必须按模型实际任务语义编写；分类模型输出 top-k 类别/分数，检测模型输出框/类别/置信度，语音模型输出文本或任务结果。不得只打印 tensor shape 或一堆原始数字作为 demo。
- `python -c "import <model_name>_sdk"` 必须通过。
- 不得调用 `ax_run_model` 实现 Python SDK 推理。

## Python SDK README.md

`TASK_DIR/sdk/python/README.md` 必须包含：

1. **环境要求**：Python 版本、系统依赖（如 libgl1）。
2. **安装步骤**：
   - 完整的 `pip install -r requirements.txt` 命令。
   - 若 `pyaxengine` 需从源码安装，给出完整的 `git clone` + `pip install` 命令。
3. **快速运行**：完整命令行示例，含输入文件格式要求。
4. **API 说明**：SDK 类的初始化参数、推理方法签名、返回值结构。
5. **输入预处理说明**：resize 策略、归一化参数、颜色通道顺序。

## C++ SDK

目录：`TASK_DIR/sdk/cpp/`

必须包含：

- `include/`
- `src/`
- `examples/`
- `CMakeLists.txt`
- `toolchain-aarch64.cmake`
- `README.md`（详见下方 [C++ SDK README.md](#c-sdk-readmemd)）

实现要求：

- CMake 支持本机构建和 aarch64 交叉编译；存在交叉编译工具链时必须执行交叉编译验证。
- C++ SDK 必须直接调用 AX Engine runtime API，并链接 `libax_engine.so`/`libax_sys.so`（或厂商包中等价的 `libaxengine.so` 命名）。
- AX runtime 头文件/库未知时，用变量占位：`AX_RUNTIME_ROOT`，目录应包含 `include/` 和 `lib/`。
- C++ 工程模板参考：https://github.com/ml-inory/Template.axera/tree/main
- 必须生成可复用 C++ 类，例如 `<ModelName>Runner`、`<ModelName>Classifier` 或任务对应命名；AX runtime 的加载、IO 分配和推理封装在类内部。
- `examples/` 中的程序只能实例化 SDK 类并调用公开方法，不应把主要推理逻辑写在 example 里。
- 示例必须按模型实际任务语义编写；分类模型输出 top-k 类别/分数，检测模型输出框/类别/置信度，语音模型输出文本或任务结果。不得只打印 tensor shape 或一堆原始数字作为 demo。
- 不得调用 `ax_run_model` 实现 C++ SDK 推理。
- 有工具链时执行交叉编译；否则至少执行 `cmake -S . -B build`。

## C++ SDK README.md

`TASK_DIR/sdk/cpp/README.md` 必须包含：

1. **环境要求**：
   - 本机构建：CMake 版本、C++ 编译器（gcc/clang）。
   - 交叉编译：aarch64 工具链的下载地址和安装方法，给出完整 URL。
   - AX runtime：头文件和库文件的获取路径，说明如何设置 `AX_RUNTIME_ROOT`。
2. **构建步骤**：
   - 本机构建（仅验证编译，不能运行推理）：
     ```
     mkdir build && cd build
     cmake .. -DCMAKE_BUILD_TYPE=Release
     make -j$(nproc)
     ```
   - 交叉编译（产物可上板运行）：
     ```
     mkdir build_arm && cd build_arm
     cmake .. -DCMAKE_TOOLCHAIN_FILE=../toolchain-aarch64.cmake -DCMAKE_BUILD_TYPE=Release
     make -j$(nproc)
     ```
3. **上板运行**：如何将编译产物传到板端、设置 `LD_LIBRARY_PATH`、运行示例。
4. **API 说明**：类的构造、初始化、推理方法、输入输出数据格式。

## 验证

- Python import 成功。
- C++ cmake configure 成功。
- Python SDK README 覆盖环境安装、运行示例、API 说明。
- C++ SDK README 覆盖本地/交叉编译、上板运行、API 说明。
- 生成 `sdk/sdk_report.md`。

## STOP

缺失必要 runtime API 信息且无法生成可编译骨架时停止，要求用户提供 SDK 运行时路径或头文件。
