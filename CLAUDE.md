# CLAUDE.md

所有回复均采用中文

工作流定义见 `.codex/workflows/axmodel-pipeline.yaml`，执行指令见 `.codex/skills/axmodel-pipeline/SKILL.md`。

# 工作流节点

ACQUIRE → INIT → EXPORT → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD（可选）→ PACKAGE

- **ACQUIRE**: 从 git/HuggingFace/本地路径获取模型到 `origin/`
- **INIT**: 初始化工作目录
- **EXPORT**: 导出 ONNX，生成 `model_meta.json`（含 I/O 元数据）
- **COMPILE**: pulsar2 编译为 axmodel
- **SIMULATE**: 仿真精度对比
- **SDK-GEN**: 并行生成 Python SDK 和 C++ SDK（aarch64 交叉编译）
- **RUNONBOARD**: 上板验证（可选）
- **PACKAGE**: 打包 axmodel + SDK + 报告

# 工作流准则

- **顺序执行**：必须按上述顺序执行，不得跳阶段。
- **强制确认**：在每个标记有 **STOP** 的地方必须获得用户确认。
- **状态记录**：所有执行过程、错误分析记录在 `task.md` 和 `analysis.md`。
- **环境隔离**：所有操作在指定任务工作目录 `TASK_DIR` 下进行。
- **问题记录**：调试中解决的问题放到 `issues/`，命名规则 `序号_模型名_阶段_问题简述.md`。
