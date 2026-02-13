---
description: Workflow COMPILE;
user-invocable: false
context: fork
agent: Plan
---

工作目录: $TASK_DIR/compile

# Pulsar2

## 使用
1. 文档说明: https://pulsar2-docs.readthedocs.io/zh-cn/latest/
2. 参考json: [templates/simple_pulsar2_config.json](templates/simple_pulsar2_config.json)
3. 禁止配置 "highest_mix_precision": true,
4. 遇到精度问题，首先查看 `https://pulsar2-docs.readthedocs.io/zh-cn/latest/appendix/precision_debug_guides.html` 排查问题；
5. 使用pulsar2的最新docker镜像, 镜像可从HuggingFace获取: https://hf-mirror.com/AXERA-TECH/Pulsar2，可通过hf_hub_download下载

## 配置
针对onnx静态图模型写转换配置json

配置文件中如果配置了 mean/std参数，则在推理时，期望输入是不做预处理的，这时要十分注意配置，在模型中只会做一次预处理；如果是pytorch模型，有些模型会先做一次 -0/255的归一化操作，而后面又会做一次归一化，比如 "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225] ，这时不能直接配置 mean/std为 [0.485, 0.456, 0.406] 和 [0.229, 0.224, 0.225]，而是它们乘上255

## 转换
执行pulsar2 build

必要的中间产物放在$TASK_DIR/cache下
若转换失败，记录错误原因，如果是onnx op不支持，带着错误信息回到EXPORT流程修改onnx模型

# task记录

在task.md中记录:
1. axmodel路径
2. 量化对分表（如有）
3. 模型的MACS
4. 模拟的max cycles
5. docker环境, pulsar2的镜像版本

完成后进入VERIFY阶段