---
name: simulate
description: Hidden stage for magnetar. Compare ONNX outputs with AXMODEL simulation outputs using task-relevant metrics.
---

# SIMULATE

## 执行

`metrics = magnetar.stages.simulate.run(task_dir, sample, pulsar_image, board=board, target_hw=TARGET_HARDWARE)`

内部逻辑：
1. 计算 ONNX 参考输出
2. **有板必上板**：BOARD 已配置直接用；未配置时先 `magnetar.board_util.select_board(TARGET_HARDWARE, BOARD_PASSWORD)` 找空闲板
3. **上板**：先 `ensure_remote_infer(board)` 确保 ax-remote-infer 已装（18500 通就跳过，未装自动静默安装），再上传模型，`/opt/bin/ax_run_model` 直接跑（秒级），下载结果与 ONNX 对比
4. **仅当找不到板或板端失败**：回退 `pulsar2 run` Docker 仿真（分钟级）

输入/输出格式（bin 命名、input_list、reshape）一律用 `magnetar/io_format.py`，规范见 `docs/input-format-cheatsheet.md`。

## LLM 分支（model_route=llm）

不再对比 ONNX vs AXMODEL 张量，改为：
1. **有板必上板**：`magnetar.stages.llm.install_axllm(board)`（ax-llm install.sh，
   已装则跳过）→ `serve_axllm(board, compile/llm_model_dir, port=8000)` 启动
   OpenAI 兼容服务 → `validate_chat("http://127.0.0.1:8000", model_name, prompts≥3,
   expected_keyword=None)` greedy 语义验证，记录响应非空 / completion_tokens /
   耗时；写 `simulate/simulate_report.md`（LLM 版：逐层 cosine + 语义验证指标）；
2. **无板回退**：用 `llm_build2 --check_level 2 --prompt <prompt>` 自带全模型校验，
   `_extract_cosims(log)` 提取 decode/prefill 逐层 cosine 写入报告；板端语义验证
   留到 RUNONBOARD，报告标注 N/A。

验收（`accuracy_gate` / `llm_route_acceptance`）：逐层 cosine min ≥ 0.99；
有板时语义验证全非空。

## 验证
- cosine_similarity ≥ 0.99
- MAE、max_abs_diff 记录在 `simulate_report.md`
- ≥3 组输入样本，报告均值 ± 标准差
- LLM 分支：逐层 cosine min ≥ 0.99 + 有板时 ≥3 组 prompt 语义验证全非空

## STOP
- cosine < 0.99：先查 `issues/` 目录已知修复；INT8/U16/混合精度全部尝试仍不达标时，STOP 前先向用户提议上 QAT（必须用官方 `AXERA-TECH/QAT.axera`，走 QAT→QDQ ONNX，需训练数据/时间，用户确认后进入）
- AXMODEL 输出全零/异常 → 检查校准归一化配置
- LLM 分支：axllm serve 无法启动 → 检查安装/模型目录/内存；仍失败 STOP
