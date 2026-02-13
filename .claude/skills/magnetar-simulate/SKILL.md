---
description: Workflow SIMULATE;
user-invocable: false
context: fork
agent: Plan
---

验证axmodel与onnx模型的输出相似度:
1. axmodel的输出通过pulsar2 run生成
2. 确保axmodel和onnx使用同样的输入
3. 测试脚本需要保留
4. 生成simulate-report.md记录测试过程和结果

**STOP** → "仿真精度是否达标？(y/n)"
确保相似度可接受以后，进入SIMULATION阶段