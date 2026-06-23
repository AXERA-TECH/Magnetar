---
description: Workflow PACKAGE;
user-invocable: false
context: fork
agent: Plan
---

打包代码，生成一个适合用户上传的git的工作目录，其中应该包括：
1. README.md  同git的README功能
2. model_convert目录  包含将模型转换到onnx的必要脚本
3. python目录 包含运行python demo的脚本
4. cpp目录  包含运行C++ demo的文件、构建系统默认用CMake
5. models目录 包含转换好的模型、配置等必要的资源文件

在RUNONBOARD步骤的板子上验证以上cpp和python的效果

**STOP** → "代码已打包到$工作目录"
全部工作已完成。