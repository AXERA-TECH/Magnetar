---
name: init
description: Hidden stage for magnetar. Initialize TASK_DIR structure, logs, and status files.
---

# INIT

## 执行
`task_dir = magnetar.stages.init.run(config)`

## 验证
- `TASK_DIR/` 下 `origin`, `export`, `compile`, `simulate`, `sdk/python`, `sdk/cpp`, `runonboard`, `package`, `cache` 目录存在
- `task.md` + `analysis.md` + `config.json` 已写入

## STOP
- 无（此阶段永远可执行）
