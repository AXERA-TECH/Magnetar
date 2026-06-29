# Task: [Model Name] Deployment

**Status:** ACQUIRE / INIT / EXPORTING / COMPILING / SIMULATING / SDK-GEN / RUNONBOARD / PACKAGING
**Agent PID:** [Bash(echo $PPID)]

## 基础信息
- **来源**: [git URL / hf://org/model / 本地路径]
- **目标芯片**: [AX650 / AX620E]
- **工作目录**: [TASK_DIR]
- **SDK语言**: [python / cpp / both]

## 实施进度
- [ ] **ACQUIRE**: 模型获取（git/HF/本地）
- [ ] **INIT**: 环境初始化
- [ ] **EXPORT**: ONNX 导出与 model_meta.json 生成
- [ ] **COMPILE**: pulsar2 编译 axmodel
- [ ] **SIMULATE**: 仿真精度对比
- [ ] **SDK-GEN**: Python + C++ SDK 生成与验证
- [ ] **RUNONBOARD**: 开发板实测验证（可选）
- [ ] **PACKAGE**: 打包产物

## 编译日志摘录
> [记录关键编译参数或报错片段]

## 精度报告
- **ONNX 输出**: [Summary]
- **axmodel 仿真输出**: [Summary]
- **余弦相似度**: [value]

## SDK 验证结果
- **Python SDK**: [import OK / 失败原因]
- **C++ SDK**: [cmake configure OK / 失败原因]

## 板端结果
- **板端推理输出**: [Summary]
- **精度偏差**: [Percentage]
