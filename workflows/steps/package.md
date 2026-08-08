# PACKAGE（yaml step id: package）

- kind: agent；skill: `.codex/skills/magnetar/hidden/package/SKILL.md`
- depends_on: `stage_review_runonboard`
- inputs: axmodel_path / axmodel_dir / model_meta_json / python_sdk_path / cpp_sdk_path /
  export_report / compile_report / simulate_report / runonboard_report / model_route
- outputs: package_dir / customer_readme / performance_report / model_convert_readme /
  python_sdk_readme / cpp_sdk_readme / model_convert_requirements / compile_script
- timeout: 300s；retry: 1 次（filesystem_transient）
- on_failure: fail
- 要点：面向小白交付包（setup.sh / run.sh 一键 + README + self_test）；
  model_convert 含可复现编译流程；SDK 不含 onnxruntime/torch 回退（NPU 专用版）
- LLM 分支：`models/` 放 axllm 模型目录（config.json + tokenizer + 逐层/post axmodel +
  embedding bin + model_meta.json）；`model_convert/` 放可复现 `llm_build.sh`
  （完整 llm_build2 命令 + embed_process.sh + config 生成）；`setup.sh` 安装 axllm，
  `run.sh` 启动 serve + 运行 OpenAI 兼容 SDK 示例；performance_report 记录
  TTFT / token 速率 / 逐层 cosine 替代张量对分指标
- 后置：`package_validation`（self_test 失败修脚本重试 ≤3 次）
