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
- pyaxengine 等 GitHub 直链依赖默认经 `GH_PROXY`（`gh_proxy_url()`）写入 requirements.txt

## 通用 SDK 生成（非 MobileNet）

优先调用：
- `magnetar.stages.sdk_gen.run_generic_python(task_dir)` → `sdk/python/<model>_sdk/`
- `magnetar.stages.sdk_gen.run_generic_cpp(task_dir, target_hw)` → `sdk/cpp/`

一致性保障（自动）：
- 模型接口（输入输出名/shape/dtype）以 `export/model_meta.json` 为权威
- 预处理/后处理与示例输入以 `origin/model_flow.json`（ACQUIRE 阶段记录）为准
- **前后处理对齐原版**：preprocess/postprocess 必须来自原版模型管线（ACQUIRE 验证过），
  **调用方式尽量对齐原版**（`model_flow.sdk_interface` 记录入口/入参顺序/输入格式/输出结构，
  example.py 镜像原版调用方式）；禁止为省事改成直通/自定义
- `example_input` 缺失、`preprocess_code`/`postprocess_code` 语法错误时抛错，
  避免生成与真实运行流程不一致的 SDK
- 生成后务必用 `example.py --model ... --input <真实样本>` 验证一次（板端或 ORT 回退）

需要自定义预处理/后处理时，在 `model_flow.json` 提供代码后重新调用生成函数。

## 发布版（NPU 专用，无 CPU 回退）

**端到端 NPU 跑通后（RUNONBOARD 报告存在），发布包内 SDK 不再保留 onnxruntime 回退**：
- `package.assemble()` 会自动把 `package/python` 下的通用 SDK 替换为 NPU-only 版
  （`inference.py` 只 import axengine，非 AX 环境直接报错并提示在板端运行）
- 交付 SDK 的依赖仅为 `numpy + pyaxengine`，不包含 onnxruntime/torch/transformers
- **依赖最小化**：交付包 Python/C++ 尽量减少依赖（C++ 只链 ax_engine/ax_sys；
  Python 只 numpy+pyaxengine），opencv/pillow 等仅当原版前处理确实需要时才进 requirements.txt
- **CPU fallback 尽量不做**：能端到端 NPU 就端到端；仅 RUNONBOARD 未跑通时才允许保留开发版回退，
  且交付说明中必须标注“未做端到端 NPU 验证”
- 源目录 `sdk/python/` 保留开发版（含 ORT 回退）供本机逻辑验证，不进交付包
- 需要严格版时也可直接调用 `run_generic_python(task_dir, strict_npu=True)`

## LLM 分支（model_route=llm）

模型是自回归/类 LLM 时，SDK 不再基于 pyaxengine，改为：
- **Python SDK**：OpenAI 兼容 HTTP 客户端——类 `LLMClient(api_url, model_name)`，
  `chat(messages, **kwargs)` / `stream()` 调 `/v1/chat/completions`；依赖**仅 requests**
  （requirements.txt 只写 `requests`，不含 pyaxengine/onnxruntime/torch/transformers）；
  调用约定对齐原模型 chat 模板（`model_flow.json` 的 sdk_interface）；
  `example.py` 启动/复用板端 `axllm serve` 后调用客户端打印回复；
- **C++ SDK**：可选，OpenAI 兼容 HTTP 客户端（libcurl），cmake configure 通过即可，
  不强求上板链接 AX runtime；
- 板端运行前置：`axllm serve <model_dir>`（RUNONBOARD 负责安装与启动）。

## 验证
- Python `import <model>_sdk` 成功
- C++ `cmake configure` 成功
- Python `example.py` 用 ACQUIRE 真实样本跑通，输出与 ONNX/板端一致
- `requirements.txt` 覆盖完整依赖
- 发布包（RUNONBOARD 通过后）SDK 不含 `import onnxruntime`，依赖仅 numpy + pyaxengine
- LLM 分支：`import <sdk>` 通过；requirements.txt 依赖仅 requests；
  对 `axllm serve` 的 `/v1/chat/completions` 冒烟一次

## STOP
- 无（此阶段总是可执行）
