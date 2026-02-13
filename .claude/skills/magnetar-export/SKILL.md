---
description: Workflow EXPORT;
user-invocable: false
context: fork
agent: Plan
---

工作目录: $TASK_DIR/export/
工作目标: 导出$TASK_DIR/origin中的模型

# 环境安装

先检查用户是否已有conda环境，扫描conda环境中是否有合适的环境，
否则使用uv包管理重新安装环境，并将虚拟环境放置在工作目录

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

脚本放到export下
执行test-torch.py确保测试通过再进行下一步

# 导出onnx(动态图)

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
5. 如果涉及多个模型，应允许分组件导出，逐个测试
6. 遇到transformer模型时，decode部分尽量使用KV Cache实现
7. 涉及修改原模型的时候使用monkeypatch，避免修改项目本身的源码
8. 添加与torch模型对分校验的功能，以确保同样的输入产生同样的输出
9. 如在README.md中已有导出ONNX的方法或者repo，直接引用或参考
10. 在遇到导出问题时可参考最佳实践(see [best_practice](best_practice.md))

输出产物应包含：
1. export-dynamic-onnx.py
2. model_structure.md，描述模型结构
3. export-dynamic-onnx.md， export-dynamic-onnx.py的使用说明 
4. workaround.md，如实现过程涉及为导出成功作出的取舍或限制，应在此处说明
5. 导出的onnx模型, 放在cache下
6. 与torch对分的脚本

脚本放到export下
若导出失败，向用户提出帮助，是否需要启动多个子agent头脑风暴提出最佳方案。
更新task.md
**STOP**

# 导出onnx(静态图)

写一个export-static-onnx.py，用于导出静态图的onnx模型

参考内容: 同 导出onnx(动态图)
遵循以下要求: 部分同 导出onnx(动态图)，例外:
1. 静态图不应再有dynamic_axes
2. 给出建议的输入长度
3. 强制设定dynamo=False

输出产物应包含：
1. export-static-onnx.py
3. export-static-onnx.md， export-dynamic-onnx.py的使用说明 
4. 更新workaround.md，如实现过程涉及为导出成功作出的取舍或限制，应在此处说明
5. 导出的onnx模型, 放在cache下
6. 与torch对分的脚本

脚本放到export下
若导出失败，向用户提出帮助，是否需要启动多个子agent头脑风暴提出最佳方案
若导出成功，与torch模型做对分校验
更新task.md
**STOP**

# 生成量化校准集

依赖onnx静态图模型
写一个generate-data.py，用于生成每个模型的输入数据
输入数据必须采用真实数据，数据来源有:
1. 从项目中寻找
2. 自行生成
3. 上述方法无效时应向用户获取，用户可以提供路径或url

generate-data.py应生成这样的目录结构:
```
calib_data/
    input_names[0]/
        data_index_0.npy
        data_index_1.npy
    input_names[1]/
    ...
```
数据生成完成后，将每个input_name下的数据压缩打包:
```
calib_data/
    input_names[0]/
    input_names[1]/
    input_names[0].tar.gz
    input_names[1].tar.gz
```

calib_data放到export下

# task记录

在task.md中记录:
1. onnx静态图模型路径
2. 量化校准集路径

完成后进入COMPILE阶段