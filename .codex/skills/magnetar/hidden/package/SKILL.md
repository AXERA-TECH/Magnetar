---
name: package
description: Hidden stage for magnetar. Assemble validated AXMODEL, SDKs, reports, and usage documentation into a customer delivery directory.
---

# PACKAGE

## 执行
`pkg = magnetar.stages.package.assemble(task_dir, metrics, pulsar_image)`

## 交付包结构

```
package/
├── README.md           # 模型概述 + 快速开始（Python/C++ 示例命令完整无省略）
├── models/
│   ├── model.axmodel
│   └── model_meta.json
├── python/             # Python SDK（基于 pyaxengine）
├── cpp/                # C++ SDK（CMake + 直接链接 AX runtime）
├── model_convert/      # export_onnx.py + pulsar2_config.json + compile_pulsar2.sh + README
│   └── README.md       # 覆盖环境准备、导出、编译、产物检查，命令可直接复制执行
└── reports/            # export/compile/simulate/runonboard 报告
```

## 分发
GitHub 给源码让客户复现，HuggingFace 给预编译让客户直接用。HF 不含 `model_convert/` 和 C++ 源码，README 需 YAML frontmatter。

## 验证
- `package/` 可独立作为 git 项目发布
- 所有 README 命令完整无省略，可直接复制执行
- 无私有凭据、缓存、虚拟环境残留
- 板端自验证：按 README 从零搭建→编译→运行，所有步骤可连续无中断执行

## STOP
- 无（此阶段总是可执行）
