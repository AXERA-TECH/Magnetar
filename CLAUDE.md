# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

所有回复均采用中文

Codex 使用说明见 `AGENTS.md` 和 `.codex/skills/magnetar-deploy/SKILL.md`。

# 工作流定义

工作流旨在通过严格顺序执行的工作流节点将原始浮点模型转换为可运行在 AX 芯片上的量化模型，并在硬件开发板上完成验证。

## 工作流节点

 - INIT: 初始化工作环境，新建工作目录
 - EXPORT: 导出onnx模型
 - COMPILE: 用pulsar2工具链编译模型
 - SIMULATE: 仿真运行
 - RUNONBOARD: 上板运行

## 工作流准则

**核心原则：**

* **顺序执行**：必须按照 INIT → EXPORT → COMPILE → SIMULATE → RUNONBOARD 顺序执行。
* **强制确认**：在每个标记有 **STOP** 的地方必须获得用户确认或输入。
* **状态记录**：所有执行过程、错误分析必须记录在 `task.md` 和 `analysis.md` 中。其中`task.md`的模板参考 @task.md
* **环境隔离**：所有操作必须在指定的任务工作目录下进行。
* **问题记录**：在调试时遇到的所有问题，解决后都放到 `issues` 目录下, 新建一个文档， 命名规则参照为`序号_模型名_阶段_问题简述.md`，如`000_mobilenet_export_acc_error.md`；
