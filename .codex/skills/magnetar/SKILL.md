---
name: magnetar
description: Convert remote or local AI models into AXera AXMODEL packages with Python and C++ SDKs for customer delivery. Use when Codex must acquire a model from Git/HuggingFace/URL/local path, export ONNX, compile with Pulsar2, simulate/validate AXMODEL accuracy, optionally run on AX hardware, generate SDKs, or package deployment artifacts.
---

# Magnetar

始终用中文沟通。Magnetar 将浮点 AI 模型转换为 AX 芯片可部署的 AXMODEL 交付包。

## 执行方式

优先调用 CLI 直接执行：

```bash
./bin/magnetar exec mobilenet
```

CLI 内部串联完整 9 阶段 pipeline（INIT → ACQUIRE → EXPORT → TOOLCHAIN → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE），不依赖 Codex。

当 CLI 执行失败、用户需要自定义模型（非 MobileNet）、或需要交互式调试时，回退到手动按阶段推进：

```
ACQUIRE → INIT → EXPORT → TOOLCHAIN → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE
```

手动模式下的约束（详见 [workflows/magnetar.yaml](../../../workflows/magnetar.yaml)）：
- 所有 9 阶段不可跳过
- BOARD 未提供时 RUNONBOARD 自动跳过
- STOP 点：SOURCE/TARGET_HARDWARE 缺失、ONNX 验证失败、Pulsar2 不可用、编译失败、精度不达标

## 配置

优先读取 `.magnetarrc` 文件，环境变量可覆盖。常用配置项：

```bash
TARGET_HARDWARE=AX650
SOURCE=<模型路径/URL>
BOARD=root@192.168.1.100   # 可选
SDK_LANG=both
```

详见 `.magnetarrc.example`。

## 目录约定

```
TASK_DIR/
  origin/       # 原始模型
  export/       # ONNX + model_meta.json + 校准数据
  compile/      # Pulsar2 配置 + model.axmodel
  simulate/     # 精度对分报告
  sdk/python/   # Python SDK
  sdk/cpp/      # C++ SDK
  runonboard/   # 板端验证
  package/      # 客户交付包
  cache/        # 中间文件
```
