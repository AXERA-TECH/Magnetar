---
name: runonboard
description: Hidden stage for magnetar. Optionally deploy AXMODEL and SDK examples to an AX board and verify runtime behavior.
---

# RUNONBOARD

## 执行
`board_metrics = magnetar.stages.runonboard.run(task_dir, sample, target_hw, pwd)`

需要 PyAXEngine 在板端可用。C++ 需先交叉编译（用 `AARCH64_GXX` 环境变量或 BSP 工具链）。

选到板后先 `ensure_remote_infer(board)`：检查 TCP 18500，daemon 未装则用官方 release 静默安装（装后可扫端口发现板子）。

## LLM 分支（model_route=llm）

1. `magnetar.stages.llm.install_axllm(board)`：板端装 ax-llm（`install.sh`，
   默认 axllm 分支，install.sh 下载经 `GH_PROXY` 代理，AX650 片上编译耗时较长，超时放宽）；
2. `serve_axllm(board, compile/llm_model_dir, port=8000)`：上传模型目录 +
   `axllm serve` 后台启动，轮询 `/health` 就绪；
3. 板端运行 Python SDK 示例（OpenAI 兼容客户端）：`validate_chat` ≥3 组 prompt
   greedy 语义验证，记录 TTFT（serve 日志 `ttft:`）/ completion_tokens / token 速率
   （`avg token/s`）/ 系统内存增量（`free -m` 前后）/ CMM 占用
   （`/proc/ax_proc/mem_cmm_info` 前后）；
4. `runonboard_report.md` 记录上述指标；语义验证失败 → 检查 tokenizer/config/
   内存预检（mem_guard）并重试 ≤3 次。

## 验证
- Python SDK 板端推理成功，Python/C++ 输出 cosine ≥ 0.98
- `runonboard_report.md` 含 board host、chip_type、延迟、内存
- LLM 分支：axllm serve 就绪 + ≥3 组 prompt 全非空 + TTFT/token 速率/内存已记录

## STOP
- 无（BOARD 未配置时自动跳过，返回 None）
- LLM 分支：axllm 安装失败（缺 gcc/网络）且无法获取预编译产物 → STOP 说明缺失项
