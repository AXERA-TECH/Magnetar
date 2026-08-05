---
name: acquire
description: Hidden stage for magnetar. Acquire a remote or local model into TASK_DIR/origin without modifying the source.
---

# ACQUIRE

## 执行
`magnetar.stages.acquire.run(task_dir, source)`

拿到模型后，**记录运行流程**：调用 `magnetar.stages.acquire.write_model_flow(task_dir, flow)`
写入 `origin/model_flow.json`，字段见函数 docstring。至少包含：
- `example_input`：真实样本路径（保证 SDK 用与验证一致的数据）
- `preprocess_code` / `postprocess_code`：预处理/后处理函数体（SDK 原样嵌入）
- `verified: true`：表示该流程已实际跑通模型

SDK-GEN 阶段必须读取此文件生成 SDK，确保与 ACQUIRE 验证过的运行流程一致；
缺失或示例样本不存在时 SDK 生成会报错。

## 验证
- `origin/` 下有模型文件或 `source.txt`
- `ACQUIRE_REPORT.md` 已生成
- `model_flow.json` 已记录运行流程（缺失时 SDK-GEN 只能生成直通预处理/后处理，需 Agent 注意）

## STOP
- SOURCE 无效（本地路径不存在、URL 不可达、Git clone 失败）
- 需要私有凭据（HF_TOKEN 缺失）
