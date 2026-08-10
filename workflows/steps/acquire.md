# ACQUIRE（yaml step id: acquire）

- kind: agent；skill: `.codex/skills/magnetar/hidden/acquire/SKILL.md`
- depends_on: `requirements_gate`
- inputs: SOURCE / HF_TOKEN / TASK_DIR / HF_ENDPOINT / GH_PROXY / PIP_INDEX_URL
- outputs: origin_path / acquire_manifest
- timeout: 900s；retry: 1 次（network_timeout / partial_download，指数退避）
- on_failure: ask_user（SOURCE 无效 / 私有凭据缺失）
- 要点：模型获取优先 ModelScope（国内 CDN）；SOURCE 为 HF repo 时先
  `modelscope_available(<id>)` 探测，有则 `modelscope download`，无才回退
  HF_ENDPOINT=hf-mirror；HF 大文件用 hfd 下载（`scripts/download_hf.sh <id>
  --local-dir origin/<name> -x 8`），小文件单线；Git URL 默认经 GH_PROXY 克隆；
  拿到模型后写 `origin/model_flow.json`
- LLM 检测：扫描 `origin/config.json` 的 architectures/model_type（含嵌套 text_config）、
  README.md 的 pipeline_tag、model_flow 的 task；命中自回归/LLM 特征时在
  manifest.json 记录 `route_hint: {"llm": true, "reason": "..."}`，
  供后置 `model_route` gate 判定（函数：`magnetar.stages.llm.classify`）
- 后置：`stage_review_acquire`（AUTO_APPROVE=true 时跳过）
