# SDK-GEN（yaml step id: sdk_gen）

- kind: agent；skill: `.codex/skills/magnetar/hidden/sdk-gen/SKILL.md`
- depends_on: `llm_route_acceptance`
- inputs: axmodel_path / axmodel_dir / model_meta_json / MODEL_NAME / cxx_toolchain_file / ax_runtime_root / model_route
- outputs: python_sdk_path / cpp_sdk_path / sdk_report
- timeout: 1800s；retry: 1 次（generation_error / validation_failed）
- on_failure: fail
- 要点：Python SDK 默认 `AxEngineExecutionProvider`；C++ SDK cmake configure 通过；
  通用版基于 model_meta + model_flow 生成
- LLM 分支：Python SDK = OpenAI 兼容 HTTP 客户端（`requests`，包依赖仅 requests，
  不含 pyaxengine/onnxruntime/torch/transformers），默认指向板端
  `http://<board>:8000/v1`，调用方式对齐原模型 chat 模板（model_flow.json 的
  sdk_interface）；C++ SDK = 可选 HTTP 客户端（libcurl），cmake configure 通过即可；
  板端运行前置：axllm serve 模型目录
- 后置：RUNONBOARD
