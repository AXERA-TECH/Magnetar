---
name: magnetar
description: Convert remote or local AI models into AXera AXMODEL packages with Python and C++ SDKs for customer delivery.
---

# Magnetar

始终用中文沟通。完整工作流和爱芯开发知识见 `AGENTS.md`。

## 执行

按顺序推进 9 阶段，每阶段读取对应 `hidden/<stage>/SKILL.md`：

```
ACQUIRE → INIT → EXPORT → TOOLCHAIN → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE
```

- 各阶段优先调用 `magnetar/stages/*.py` 工具函数
- 遇到 STOP 点暂停等用户确认
- BOARD 未配置时 RUNONBOARD 自动跳过
- 回退/重试/循环逻辑由 `workflows/magnetar.yaml` 状态机控制

## 配置

读取 `.magnetarrc`（shell 风格 key=value），环境变量可覆盖。详见 `.magnetarrc.example`。
