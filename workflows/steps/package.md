# PACKAGE（yaml step id: package）

- kind: agent；skill: `.codex/skills/magnetar/hidden/package/SKILL.md`
- depends_on: `stage_review_runonboard`
- inputs: axmodel_path / model_meta_json / python_sdk_path / cpp_sdk_path / export_report /
  compile_report / simulate_report / runonboard_report
- outputs: package_dir / customer_readme / performance_report / model_convert_readme /
  python_sdk_readme / cpp_sdk_readme / model_convert_requirements / compile_script
- timeout: 300s；retry: 1 次（filesystem_transient）
- on_failure: fail
- 要点：面向小白交付包（setup.sh / run.sh 一键 + README + self_test）；
  model_convert 含可复现编译流程；SDK 不含 onnxruntime/torch 回退（NPU 专用版）
- 后置：`package_validation`（self_test 失败修脚本重试 ≤3 次）
