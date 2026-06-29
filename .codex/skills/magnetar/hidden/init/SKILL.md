---
name: init
description: Hidden stage for magnetar. Initialize TASK_DIR structure, logs, status files, and stage directories.
---

# INIT

目标：创建隔离工作目录和审计文件。

## 目录结构

```text
TASK_DIR/
  origin/
  export/
  compile/
  simulate/
  sdk/
    python/
    cpp/
  runonboard/
  package/
  cache/
    acquire/
    toolchain/
  task.md
  analysis.md
```

## 步骤

1. 若 `TASK_DIR` 未指定，创建 `todos/work/<timestamp>-<model-name>/`。
2. 初始化所有目录，保留 `origin/` 中 ACQUIRE 产物。
3. 写入 `task.md`：
   - 任务目标
   - 输入参数
   - 阶段状态表
   - 当前阶段 `INIT`
4. 写入 `analysis.md`：
   - 模型来源
   - 目标芯片
   - 已知约束和假设
5. 记录环境摘要：Python、pip/uv、docker、pulsar2、cmake、git。

## STOP

初始化后如果缺少 `TARGET_HARDWARE` 或模型主文件，停止等待用户补充。
