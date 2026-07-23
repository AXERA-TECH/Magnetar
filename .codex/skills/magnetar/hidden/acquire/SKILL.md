---
name: acquire
description: Hidden stage for magnetar. Acquire a remote or local model into TASK_DIR/origin without modifying the source.
---

# ACQUIRE

## 执行
`magnetar.stages.acquire.run(task_dir, source)`

## 验证
- `origin/` 下有模型文件或 `source.txt`
- `ACQUIRE_REPORT.md` 已生成

## STOP
- SOURCE 无效（本地路径不存在、URL 不可达、Git clone 失败）
- 需要私有凭据（HF_TOKEN 缺失）
