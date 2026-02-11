# Task: [Model Name] Deployment

**Status:** INIT / EXPORTING / COMPILING / RUNNING
**Agent PID:** [Bash(echo $PPID)]

## 基础信息
- **原始模型**: [Path/URL]
- **目标芯片**: [e.g. AX620E / AX650]
- **工作目录**: [TASK_DIR]

## 实施进度
- [ ] **INIT**: 环境检查与资源下载
- [ ] **EXPORT**: ONNX 导出与验证
- [ ] **COMPILE**: pulsar2 编译 axmodel
- [ ] **SIMULATION**: 仿真精度对比
- [ ] **RUNONBOARD**: 开发板实测验证

## 编译日志摘录
> [记录关键的编译参数或报错片段]

## 运行结果
- **浮点模型输出**: [Summary]
- **板端模型输出**: [Summary]
- **精度偏差**: [Percentage]