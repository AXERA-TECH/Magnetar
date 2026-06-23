---
description: Workflow RUNONBOARD;
user-invocable: false
context: fork
agent: Plan
---

向用户征求一个板子的ssh登录方式，在上面运行ax_run_model

验证板上axmodel与pulsar2仿真的输出相似度:
1. axmodel的输出通过ax_run_model生成
2. 确保axmodel和pulsar2 run使用同样的输入
3. 测试脚本需要保留
4. 生成runonboard-report.md记录测试过程和结果

**STOP** → "板上精度是否达标？(y/n)"
确保相似度可接受以后，进入PACKAGE阶段