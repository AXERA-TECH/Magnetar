---
name: compile
description: Hidden stage for magnetar. Compile static ONNX to AXMODEL with Pulsar2 and record compile artifacts.
---

# COMPILE

目标：用 Pulsar2 把 `export/model.onnx` 编译为 `compile/model.axmodel`，并采集编译效率指标。

## 步骤

1. 读取 `export/model_meta.json` 和校准集。
2. 生成 `compile/pulsar2_config.json`，至少明确：
   - `input`
   - `output_dir`
   - `output_name`
   - `target_hardware`
   - `input_shapes`
   - `quant.input_configs`
   - `input_processors`
3. 禁止配置 `"highest_mix_precision": true`。
   - 建议开启 `"precision_analysis": true` 获取逐层量化精度分布，结果写入 `compile/` 目录并引用到 `compile_report.md`。
4. 确认 mean/std、layout、dtype 与 EXPORT 预处理链一致。
5. 执行 `pulsar2 build` 或 Docker 等价命令。
   - 记录编译 wall-time：命令前后取 `date +%s` 差值。
6. 保存日志到 `compile/compile.log`。
7. 从 `compile.log` 或 `build_context.json` 提取性能数据：
   - MACs：搜索 `macs`、`total macs` 关键词或解析 `build_context.json` 中的 `macs` 字段。
   - 编译耗时：优先从 `build_context.json` 的 `build_time` 字段读取，无此字段时使用命令计时。
   - AXMODEL 文件大小：`du -b compile/model.axmodel` 或 `stat --format=%s`。
8. 读取 `export/model_meta.json` 的 `onnx_size_bytes`，计算压缩比 = ONNX 大小 / AXMODEL 大小。
9. 计算 MACs 利用率：若 Pulsar2 报告的是每推理 MACs 总量，记录原始值；利用率仅在有芯片理论峰值时计算（AX650 NPU 约 7.2 TOPS）。
10. 生成 `compile/compile_report.md`，至少包含：
   - Pulsar2 版本
   - 编译配置摘要
   - 编译耗时（秒）
   - MACs 数值
   - ONNX 大小（字节）、AXMODEL 大小（字节）、压缩比
   - 量化信息（精度分析结果如已开启）

## 验证

- `compile/model.axmodel` 存在且非空。
- `compile/compile_report.md` 包含 MACs、文件大小、压缩比、编译耗时。
- 编译配置、ONNX、校准数据路径可追溯。

## STOP

- Pulsar2 不可用。
- 编译失败且需要改 ONNX 或换导出策略。
- 发现输入预处理配置与导出验证不一致。
