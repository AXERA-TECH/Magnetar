---
name: compile
description: Hidden stage for magnetar. Compile static ONNX to AXMODEL with Pulsar2 and record compile artifacts.
---

# COMPILE

目标：用 Pulsar2 把 `export/model.onnx` 编译为 `compile/model.axmodel`，并采集编译效率指标。

## 校准归一化对齐（关键）

Pulsar2 校准的归一化公式为 `(image - calibration_mean) / calibration_std`，而 libdet.axera 推理预处理使用 `(input - mean) * std`。两者公式不同，必须反向对齐才能让模型收到正确范围的输入。

### ONNX 模型期望 [0,1] 输入（默认情况）

大多数 PyTorch 训练的模型期望 [0,1] 浮点输入：

| 组件 | 配置 | 输入范围 |
|------|------|----------|
| Pulsar2 校准 | `calibration_std = 255` | uint8 / 255 = [0,1] |
| libdet 推理 | `std = 1/255` | uint8 × (1/255) = [0,1] |

**常见错误**：把 `calibration_std` 设为 `0.004`（即 1/255），Pulsar2 执行 uint8/0.004 = [0,65025]，量化模型被校准到错误范围，推理时输出全零或全饱和。

### 校验方法

编译前用实际校准图跑 ONNX Runtime，分别输入 [0,1] 和 [0,255]，对比输出 cosine。若 < 0.99，模型对输入范围敏感，必须确保校准归一化匹配 ONNX 期望范围。

### 量化位宽

默认 INT8。U16 仅在 INT8 仿真 cosine < 0.99 或板端检测结果异常时尝试，且必须经板端验证确认改善后采用。

## 入口检查

进入 COMPILE 前必须确认 `export/model.onnx` 已为静态 shape。Pulsar2 不接受动态维度——`input_shapes` 配置无法覆盖 ONNX 图中定义的动态维度名。若模型仍含动态维度，必须退回 EXPORT 阶段完成静态化。

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
