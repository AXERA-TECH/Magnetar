---
name: package
description: Hidden stage for magnetar. Assemble validated AXMODEL, SDKs, reports, and usage documentation into a customer delivery directory.
---

# PACKAGE

目标：整理客户交付目录 `TASK_DIR/package/`。

## 步骤

1. 清空并重建 `package/`。
2. 复制：
   - `compile/model.axmodel` -> `package/models/model.axmodel`
   - `export/model_meta.json` -> `package/models/model_meta.json`
   - `sdk/python/` -> `package/sdk/python/`
   - `sdk/cpp/` -> `package/sdk/cpp/`
   - 阶段报告 -> `package/reports/`
   - `task.md`、`analysis.md`
3. 生成 `package/README.md`，包含：
   - 模型来源和目标芯片
   - 目录说明
   - Python 示例运行方法
   - C++ 构建和交叉编译方法
   - 输入输出 tensor 信息
   - 精度和板端验证状态
   - 已知限制
4. 可选生成 `package/manifest.json`，列出文件 SHA256、版本、时间戳。

## 验证

- 必需文件齐全。
- README 不依赖内部临时路径才能理解。
- package 中不包含原始私有凭据、缓存、虚拟环境、node_modules 或大型无关中间文件。
