# Magnetar

Pulsar2 简介

  Pulsar2 是由https://www.axera-tech.com/自主研发的新一代神经网络编译器，是
  一个"all-in-one"的工具链，集成了转换、量化、编译、异构四大功能于一体。

  核心功能

  Pulsar2的核心功能是将.onnx模型编译成AXERA芯片能够解析并运行的.axmodel模型
  文件。具体包括：

  1. 模型转换：支持将ONNX格式的模型转换为AX芯片专有格式
  2. 量化优化：对模型进行量化处理，提升推理效率
  3. 编译优化：针对AX系列芯片架构进行深度优化编译
  4. 异构计算：充分利用CPU+NPU异构计算单元算力

  支持的芯片平台

  Pulsar2针对爱芯元智新一代AX6、M7、M5系列芯片进行了深度定制优化，支持包括：

  - AX6系列：AX615、AX630C、AX637、AX620Q、AX650A、AX650N
  - M7系列：M76H
  - M5系列：M57H

  虚拟NPU (vNPU) 架构

  Pulsar2支持AXERA芯片的虚拟NPU架构，能够灵活配置NPU工作模式：

  - AX650/M76H：3组vNPU，可配置为1+1+1对称模式、2+1大小核模式或3大算力单vNPU
  模式
  - AX620E系列：双核NPU设计，根据AI-ISP工况配置不同算力模式
  - AX615：双核NPU设计，采用通元6.0 NPU引擎

  在AX-Samples工作流中的角色

  从项目工作流（.claude/commands/cl_axsamples.md）可以看出，Pulsar2在模型部
  署流程中处于COMPILE阶段：

  1. INIT → EXPORT → COMPILE → VERIFY → SIMULATION → RUNONBOARD
  2. 在COMPILE阶段使用pulsar2 build命令将ONNX模型编译为compiled.axmodel
  3. 编译产物在后续阶段用于仿真验证和板端实际运行

  主要价值

  - 高效部署：实现深度学习神经网络模型的快速、高效部署
  - 算力优化：充分发挥片上异构计算单元(CPU+NPU)算力
  - 灵活性：支持多种芯片平台和不同的vNPU配置模式
  - 完整性：提供从模型转换到板端部署的全流程工具支持

  部署流程

  graph LR
      ONNX模型 --> Pulsar2编译 --> AXMODEL --> 仿真验证 --> 板端运行

  来源：https://pulsar2-docs.readthedocs.io/zh-cn/latest/pulsar2/introduction.html
