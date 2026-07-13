# 001_F5-TTS_COMPILE_AxQuantizedLayerNorm_blocked

## 问题

Pulsar2 v5.1/v6.0 编译 F5-TTS DiT ONNX 时，native parser 解析 AxQuantizedLayerNorm 算子失败，报 `IndexError: list index out of range`。

## 环境

- Pulsar2: v5.1, v6.0-lite, 20260520-temp
- Target: AX650 NPU3
- ONNX 导出: PyTorch 2.12 dynamo export, opset 17
- 模型: F5-TTS DiT Transformer, dim=1024, depth=22

## 尝试过的修复

1. 修改 ONNX LayerNorm axis (-1 → 2): 无效
2. 修改 quant_axmodel dim (-1 → 1024): 无效
3. FP32 全模型量化: 无效
4. INT8 MinMax 量化: 无效
5. 移除 Neg op (→Mul): 无效
6. 移除 Constant op (→dynamo export): 无效

## 根因推测

Pulsar2 quantizer 将 LayerNormalization 转换为 AxQuantizedLayerNorm 时，某些属性格式不被 native parser 接受。

## 建议

- 反馈给 AXera Pulsar2 团队
- 尝试 ax-llm 构建流程 (专门支持 Transformer)
- 或等待 Pulsar2 修复
