---
name: sdk-gen
description: Hidden stage for magnetar. Generate customer-facing Python and C++ inference SDKs from model_meta.json and AXMODEL artifacts.
---

# SDK-GEN

## 执行
MobileNet 直接调用：
- `magnetar.stages.sdk_gen.run_mobilenet_python(task_dir, labels)`
- `magnetar.stages.sdk_gen.run_mobilenet_cpp(task_dir, target_hw)`

其他模型 Agent 自行实现。关键要求：
- Python：`pyaxengine.AxEngineExecutionProvider` 为默认 provider，`import <sdk>` 通过
- C++：CMake 直接链接 `ax_engine`/`ax_sys`（不用 FetchContent），cmake configure 通过
- YOLO 系列：集成 libdet.axera，`requirements.txt` 注明 `git clone` 获取方式

## 验证
- Python `import <model>_sdk` 成功
- C++ `cmake configure` 成功
- `requirements.txt` 覆盖完整依赖

## STOP
- 无（此阶段总是可执行）
