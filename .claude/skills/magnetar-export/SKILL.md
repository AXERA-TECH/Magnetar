---
description: Workflow EXPORT;
user-invocable: false
context: fork
agent: Plan
---

工作目录: $TASK_DIR/origin/

# 环境安装

使用uv包管理，将虚拟环境放置在工作目录

以下库使用这些版本:
1. numpy: use numpy < 2.0
2. torch: use cpu version if possible, version should be <= 2.6

添加这些库:
1. onnxruntime
2. onnx
3. onnxscript

# Torch demo

阅读README.md(如果有)，写一个使用原模型的torch python demo，有以下要求：
1. 使用argparse传参，尽量带默认参数
2. 输出一个test-torch.md描述脚本使用
3. 输出到test-torch.py

# 导出onnx(dynamic)

写一个export-dynamic-onnx.py，用于导出动态shape的onnx模型

参考内容：
1. test-torch.py，以确认输入输出
2. README.md，以理解模型结构
3. 模型结构对应的源码
4. 如项目中有导出onnx的脚本可挪用
5. 项目中的测试代码

遵循以下要求：
1. 使用argparse传参，尽量带默认参数
2. 对于有多种配置的模型，需要将它们区别，用argparse参数体现
3. torch.onnx.export使用dynamic_axes参数时，指定dynamo=False
4. 对于动态长度的输入需要在argparse参数体现
5. 如果涉及多个模型，应允许分别导出，逐个测试
6. 遇到transformer模型时，decode部分尽量使用KV Cache实现
7. 涉及修改原模型的时候使用monkeypatch，避免修改项目本身的源码
8. 添加与torch模型对分校验的功能，以确保同样的输入产生同样的输出

输出产物应包含：
1. export-dynamic-onnx.py
2. model_structure.md，描述模型结构
3. export-dynamic-onnx.md， export-dynamic-onnx.py的使用说明 
4. workaround.md，如实现过程涉及为导出成功作出的取舍或限制，应在此处说明

若导出失败，向用户提出帮助，是否需要启动多个子agent头脑风暴提出最佳方案。