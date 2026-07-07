---
name: package
description: Hidden stage for magnetar. Assemble validated AXMODEL, SDKs, reports, and usage documentation into a customer delivery directory.
---

# PACKAGE

目标：整理客户交付目录 `TASK_DIR/package/`，该目录必须是一个可独立成为 git 仓库的项目根目录，形态参考客户可直接 clone/build/run 的项目，而不是内部流水线缓存目录。

## 步骤

1. 清空并重建 `package/`。
2. 复制：
   - `compile/model.axmodel` -> `package/models/model.axmodel`
   - `export/model_meta.json` -> `package/models/model_meta.json`
   - `sdk/python/` -> `package/python/`
   - `sdk/cpp/` -> `package/cpp/`
   - ONNX 导出脚本、ONNX 产物、Pulsar2 配置、编译命令说明 -> `package/model_convert/`
   - 阶段报告 -> `package/reports/`
   - `task.md`、`analysis.md`
3. 生成 `package/reports/performance_report.md`，汇总所有阶段采集的性能数据。从各阶段报告中提取：
   - **流水线耗时**：从 `task.md` 提取各阶段耗时，计算端到端总耗时。
   - **模型效率**：从 `compile_report.md` 提取 ONNX 大小、AXMODEL 大小、压缩比、MACs。若已知芯片理论算力，计算 MACs 利用率。
   - **推理延迟**：从 `simulate_report.md` 提取仿真延迟；从 `runonboard_report.md` 提取板端 Python/C++ 延迟。
   - **板端内存**：从 `runonboard_report.md` 提取系统内存增量和 CMM 占用（若已采集）。
   - **精度汇总**：从 `simulate_report.md` 提取多输入指标均值 ± 标准差。
   
   格式参考：
   ```markdown
   # Performance Report

   ## 流水线耗时
   | 阶段 | 耗时(s) |
   |------|---------|
   | ACQUIRE | X |
   | INIT | X |
   | EXPORT | X |
   | TOOLCHAIN | X |
   | COMPILE | X |
   | SIMULATE | X |
   | SDK-GEN | X |
   | RUNONBOARD | X（或 skipped） |
   | PACKAGE | X |
   | **总计** | X |

   ## 模型效率
   - ONNX 大小: X MB
   - AXMODEL 大小: X MB
   - 压缩比: X:1
   - MACs: X G
   - MACs 利用率: X%（若可计算）

   ## 推理延迟
   - 仿真 (pulsar2 run): X ms
   - 板端 Python SDK: X ms（或 N/A）
   - 板端 C++ SDK: X ms（或 N/A）

   ## 板端内存
   - 系统内存增量: X MB（或 N/A）
   - CMM 占用: X MB（或 N/A）

   ## 精度汇总（多输入，均值 ± 标准差）
   | 指标 | 值 |
   |------|-----|
   | cosine | 0.XXX ± 0.00X |
   | MAE | X.XXX ± X.XXX |
   | max abs diff | X.XXX ± X.XXX |
   ```
4. 生成 `package/README.md`，包含：
   - 模型来源和目标芯片
   - 目录说明
   - Python 示例运行方法
   - C++ 构建和交叉编译方法
   - 输入输出 tensor 信息
   - 精度和板端验证状态
   - 性能摘要（引用 `reports/performance_report.md`）
   - 已知限制
5. 生成项目级辅助文件：
   - `.gitignore`: 忽略 Python 缓存、CMake build、临时输出文件。
   - 可选 `manifest.json`: 列出文件 SHA256、版本、时间戳。

## 推荐目录

```text
package/
  README.md
  .gitignore
  models/
    model.axmodel
    model_meta.json
  python/
    requirements.txt
    <model>_sdk/
    README.md
  cpp/
    CMakeLists.txt
    toolchain-aarch64.cmake
    examples/
    README.md
  model_convert/
    README.md
    export_onnx.py
    model.onnx
    model_meta.json
    pulsar2_config.json
    compile_pulsar2.sh
  reports/
    performance_report.md
  task.md
  analysis.md
```

## model_convert 要求

- 必须说明 ONNX 如何得到，包括导出脚本入口、依赖和静态 shape。
- 必须包含实际使用的 Pulsar2 配置文件，明确 `target_hardware`、输入 shape、dtype、layout、mean/std、calibration 设置。
- 必须保留或说明校准数据来源；如不随包提供校准数据，应在 README 写明如何重新生成。
- 不得开启 `"highest_mix_precision": true`。

## 验证

- 必需文件齐全。
- `package/reports/performance_report.md` 存在且各节内容完整（缺失数据标 N/A）。
- `package/` 可作为项目根目录阅读和构建，客户不需要理解 `TASK_DIR` 内部结构。
- README 不依赖内部临时路径才能理解。
- package 中不包含原始私有凭据、缓存、虚拟环境、node_modules 或大型无关中间文件。
