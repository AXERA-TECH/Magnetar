---
name: export
description: Hidden stage for magnetar. Export the acquired model to static-shape ONNX, validate it against the source model, and generate model_meta.json plus calibration data.
---

# EXPORT

## 执行
MobileNet 可直接调用 `sample = magnetar.stages.export.run_mobilenet(task_dir)`。
其他模型需 Agent 自行实现：导出静态 ONNX → onnx.checker 验证 → ONNX Runtime 与原模型对分（cosine ≥ 0.99）→ 生成 `model_meta.json` 和校准数据。
校准数据**尽量用真实业务数据**（`run_generic(calibration_data=…)` 或 `scripts/export_onnx.py --calib-dir`）；
随机/扰动数据仅兜底，需在 export_report.md 标注来源。

## LLM 分支（model_route=llm，自回归/类 LLM 模型）

**不导出 ONNX**，改为：
1. 验证 HuggingFace 权重可推理：跑通一次 source 生成（greedy），保存参考输出到
   `export/llm_reference.txt` 或 npy；
2. 生成可复现 `export/llm_build.sh`：完整 `pulsar2 llm_build2` 命令
   （`--input_path origin/<model> --output_path compile/llm_out --chip <chip>
   --max_context <LLM_MAX_CONTEXT> --prefill_len ... --weight_type s8|s4
   --hidden_state_type bf16`，Pulsar2 ≥ 6.0）；
3. 确认 tokenizer：origin 中已有 `tokenizer.txt`/`*_tokenizer.txt` 直接用；
   没有则按 ax-llm 文档从 HF tokenizer 转换（`third_party/tokenizer.axera` 工具），
   无法生成时 STOP 说明；
4. 记录模型参数（model_type、num_hidden_layers、hidden_size、vocab_size、
   tokenizer_type）到 export_report.md。

hybrid 组合模型（AR-TTS 等）：LLM/AR 子模型按本分支准备，非 LLM 子模型
（vocoder/encoder 等）继续走本文件上方的通用 ONNX 导出，拆分开的产物分别记录。

## 验证
- `export/model.onnx` 为静态 shape，onnxruntime 可加载
- `export/model_meta.json` 含完整 input/output name/shape/dtype/layout
- Torch/ONNX cosine ≥ 0.99
- `export/calib_data/input.tar.gz` 存在（≥3 组样本）
- `export/export_report.md` 标注校准来源（real 业务数据 / perturbed 兜底）
- LLM 分支：`export/llm_build.sh` 存在且命令完整可复制；参考输出已保存；
  tokenizer 已确认

## STOP
- ONNX 对分失败（cosine < 0.99）
- 模型含动态 shape 且静态化失败
- 仅有随机/扰动校准数据且用户未确认（校准集应尽量用真实业务数据，随机数据可能在真实业务上崩）
- LLM 分支：tokenizer 无法生成；llm_build2 不支持该架构且用户未确认回退方向
