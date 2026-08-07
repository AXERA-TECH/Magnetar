# SDK-GEN（yaml step id: sdk_gen）

- kind: agent；skill: `.codex/skills/magnetar/hidden/sdk-gen/SKILL.md`
- depends_on: `accuracy_gate`
- inputs: axmodel_path / model_meta_json / MODEL_NAME / cxx_toolchain_file / ax_runtime_root
- outputs: python_sdk_path / cpp_sdk_path / sdk_report
- timeout: 1800s；retry: 1 次（generation_error / validation_failed）
- on_failure: fail
- 要点：Python SDK 默认 `AxEngineExecutionProvider`；C++ SDK cmake configure 通过；
  通用版基于 model_meta + model_flow 生成
- 后置：RUNONBOARD
