---
description: Workflow INIT; Initialize basic structure of TASK_DIR
user-invocable: false
---

按照以下目录结构新建文件夹:

$TASK_DIR: 
    - ax-samples/   # axmodel推理demo
    - cache/        # 中间产物和debug用文件
    - compile/      # COMPIlE workflow 工作目录
    - origin/       # EXPORT workflow工作目录以及 $REPO所在位置
    - logs/         # 放置每个workflow节点的日志
    - analysis.md   # 错误分析
    - task.md

clone或拷贝$REPO到origin/下