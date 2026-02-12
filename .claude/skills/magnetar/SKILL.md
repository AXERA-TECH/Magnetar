---
description: Orchestrator of the workflow, manage workflow status and pass arguments.
---

按照Workflow节点: INIT → EXPORT → COMPILE → VERIFY → SIMULATION → RUNONBOARD 严格顺序执行

每个节点调用对应的Skill:
 - INIT: magnetar-init
 - EXPORT: magnetar-export
 - COMPILE: magnetar-compile
 - VERIFY: magnetar-verify
 - SIMULATION: magnetar-simulate
 - RUNONBOARD: magnetar-runonboard

Skill参数，作为公共参数传入每个Skill:
 - REPO: git repo url或本地路径，表示浮点模型的工程地址
 - TASK_DIR: 工作根目录，若没有指定则使用./todos/

从git repo url或本地路径抽取model_name作为项目缩写，以方便与其他项目区分
TASK_DIR = TASK_DIR / model_name