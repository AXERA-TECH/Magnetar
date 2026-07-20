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
5. 检查 `uv` 可用性；缺少 `uv` 时 STOP，不得降级到 `python -m venv`、`virtualenv` 或 `conda`。
6. 记录环境摘要：Python、uv、docker、pulsar2、cmake、git。
7. 检查磁盘空间：计算所需存储（BSP SDK ~5 GB + Docker 镜像 ~3 GB + 模型文件 + 中间产物），与当前可用磁盘空间比较。若剩余空间不足所需 1.5 倍，在 `analysis.md` 中记录警告但继续；若不足所需空间，STOP 并告知用户释放空间。

## Python 环境约束

- 所有任务虚拟环境必须位于 `TASK_DIR` 内，并用 `uv venv <path>` 创建。
- 所有依赖安装必须用 `uv pip install --python <venv>/bin/python ...`。
- 禁止使用 `python -m venv`、`virtualenv` 或 `conda` 创建/管理任务环境。

## STOP

初始化后如果缺少 `TARGET_HARDWARE` 或模型主文件，停止等待用户补充。
