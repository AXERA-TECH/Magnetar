---
name: sdk-gen
description: Hidden stage for magnetar. Generate customer-facing Python and C++ inference SDKs from model_meta.json and AXMODEL artifacts.
---

# SDK-GEN

目标：生成客户可直接集成的 Python/C++ SDK。

## Python SDK

目录：`TASK_DIR/sdk/python/<model_name>_sdk/`

必须包含：

- `__init__.py`
- `inference.py`
- `preprocess.py`
- `postprocess.py`
- `example.py`
- `README.md`
- `requirements.txt`

实现要求：

- 必须使用 `pyaxengine` 的 `axengine.InferenceSession` 运行 AXMODEL。
- 默认 provider 必须显式设置为 `AxEngineExecutionProvider`；该 provider 不可用时，才允许按 `axengine.get_available_providers()` 选择 fallback provider，并在报告中记录。
- `requirements.txt` 必须说明 `pyaxengine` 来源：`https://github.com/AXERA-TECH/pyaxengine`。
- 从 `model_meta.json` 读取输入输出信息，不硬编码无法追溯的 shape。
- 包含最小可运行示例。
- `python -c "import <model_name>_sdk"` 必须通过。
- 不得调用 `ax_run_model` 实现 Python SDK 推理。

## C++ SDK

目录：`TASK_DIR/sdk/cpp/`

必须包含：

- `include/`
- `src/`
- `examples/`
- `CMakeLists.txt`
- `toolchain-aarch64.cmake`
- `README.md`

实现要求：

- CMake 支持本机构建和 aarch64 交叉编译；存在交叉编译工具链时必须执行交叉编译验证。
- C++ SDK 必须直接调用 AX Engine runtime API，并链接 `libax_engine.so`/`libax_sys.so`（或厂商包中等价的 `libaxengine.so` 命名）。
- AX runtime 头文件/库未知时，用变量占位：`AX_RUNTIME_ROOT`，目录应包含 `include/` 和 `lib/`。
- 示例展示加载 axmodel、准备输入、运行推理、读取输出。
- 不得调用 `ax_run_model` 实现 C++ SDK 推理。
- 有工具链时执行交叉编译；否则至少执行 `cmake -S . -B build`.

## 验证

- Python import 成功。
- C++ cmake configure 成功。
- 生成 `sdk/sdk_report.md`。

## STOP

缺失必要 runtime API 信息且无法生成可编译骨架时停止，要求用户提供 SDK 运行时路径或头文件。
