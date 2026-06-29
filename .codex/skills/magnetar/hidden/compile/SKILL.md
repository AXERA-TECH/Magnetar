---
name: compile
description: Hidden stage for magnetar. Compile static ONNX to AXMODEL with Pulsar2 and record compile artifacts.
---

# COMPILE

目标：用 Pulsar2 把 `export/model.onnx` 编译为 `compile/model.axmodel`。

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
4. 确认 mean/std、layout、dtype 与 EXPORT 预处理链一致。
5. 执行 `pulsar2 build` 或 Docker 等价命令。
6. 保存日志到 `compile/compile.log`。
7. 生成 `compile/compile_report.md`，记录 Pulsar2 版本、配置、MACS/max cycles、量化信息。

## 验证

- `compile/model.axmodel` 存在且非空。
- 编译配置、ONNX、校准数据路径可追溯。

## STOP

- Pulsar2 不可用。
- 编译失败且需要改 ONNX 或换导出策略。
- 发现输入预处理配置与导出验证不一致。
