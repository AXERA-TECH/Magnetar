---
name: package
description: Hidden stage for magnetar. Assemble validated AXMODEL, SDKs, reports, and usage documentation into a customer delivery directory.
---

# PACKAGE

## 设计理念

交付包面向**零基础小白用户**。假设用户只会：
1. 打开终端
2. 复制粘贴命令
3. 按回车

因此 README 必须极简、脚本必须一键跑通、所有命令必须完整可复制。

## 执行
```python
pkg = magnetar.stages.package.assemble(task_dir, metrics, pulsar_image, model_name, labels)
```

## 交付包结构

```
package/
├── README.md           # 面向小白：两步跑起来（setup.sh → run.sh）
├── setup.sh            # 一键环境安装
├── run.sh              # 一键推理运行
├── models/
│   ├── model.axmodel
│   └── model_meta.json
├── python/             # Python SDK（基于 pyaxengine）
│   ├── demo.py         # 最简单的推理示例（复制即用）
│   └── requirements.txt
├── cpp/                # C++ SDK（CMake + 直接链接 AX runtime）
├── model_convert/      # export_onnx.py + pulsar2_config.json + compile_pulsar2.sh + README
│   └── README.md       # 覆盖环境准备、导出、编译、产物检查，命令可直接复制执行
└── reports/            # export/compile/simulate/runonboard 报告
```

## README 编写规范

- **开头一句话说清这是什么模型**（精度 + 速度 + 大小）
- **快速开始不超过 2 步**：`bash setup.sh` → `bash run.sh`
- **不要出现占位符**（如 `...`、`<path>`、`<fill me>`）
- **不要出现术语堆砌**，必要时用 FAQ 解释
- **所有代码块必须可直接复制粘贴执行**

## 一键脚本规范

### setup.sh
- 安装 Python 依赖（pip install -r requirements.txt）
- 检查必要组件（pyaxengine 等）
- 打印明确成功/失败提示

### run.sh
- 调用 `python/demo.py` 或等价入口
- 无需额外参数（若需图片则内置默认或从 models/ 取）
- 输出清晰可读

## 自测

`assemble()` 完成后，**必须**调用 `self_test()`：

```python
result = magnetar.stages.package.self_test(pkg, model_name)
```

`self_test` 会在临时目录中模拟小白用户：
1. 只读 README.md
2. 运行 `bash setup.sh`
3. 运行 `bash run.sh`
4. 检查是否全部通过

若 `result["ok"]` 为 False：
- 根据 `result["errors"]` 修正 README/脚本/setup.sh/run.sh
- 重新调用 `self_test()`，直到通过

## 分发
GitHub 给源码让客户复现，HuggingFace 给预编译让客户直接用。HF 不含 `model_convert/` 和 C++ 源码，README 需 YAML frontmatter。

## 验证
- `package/` 可独立作为 git 项目发布
- `self_test()` 通过（小白只看 README 复现成功）
- 所有 README 命令完整无省略，可直接复制执行
- 无私有凭据、缓存、虚拟环境残留

## STOP
- 无（此阶段总是可执行）
- `self_test()` 失败时自动修→重试，直到通过或 Agent 确认无法自动修复为止
