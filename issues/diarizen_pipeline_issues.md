# DiariZen EXPORT opset17 LayerNormalization 导出失败

## 现象

`torch.onnx.export` 使用 opset 17 导出 DiariZen WavLM segmentation 模型时，ONNX checker 报错：

```text
Node (/LayerNormalization)'s input 1 is marked single but has an empty string in the graph
```

## 原因判断

PyTorch 2.1.1 在 opset 17 下会将部分归一化导出为 `LayerNormalization` 节点，该图在当前 ONNX checker 中存在空输入兼容问题。

## 解决方案

将导出 opset 降为 16，使 LayerNorm 分解为基础算子。修复后 ONNX checker 与 ONNXRuntime 均通过，对分指标：cosine 约 1.0，MAE 约 1.45e-5。
# DiariZen COMPILE attention Gather tiling 失败

## 现象

DiariZen WavLM segmentation ONNX 在 AX650/NPU3 上编译时，Pulsar2 完成 ONNX parse 与量化，但 NPU backend tiling 失败：

```text
ErrorCode.NPUBackendError: TileFailException
op: /layers.0/attention/Gather_1
input tensor shape: (1, 16, 799, 799)
mem_limit: workspace=524288, max_mem_size=11530240
```

## 环境

- Pulsar2 image: `pulsar2:20260520-temp-61099061-lite`
- Target: `AX650`
- NPU mode: `NPU3`
- Input shape: `[1, 1, 256000]`，16 秒音频
- Export opset: 16

## 原因判断

16 秒输入经过 WavLM frontend 后产生约 799 帧，自注意力子图产生 `(1,16,799,799)` 的二次复杂度张量。当前 AX650 NPU backend 对该 attention/Gather tiling 模式无法通过。

## 后续策略

- 降低静态 segment duration，例如 4s/8s 后重新导出编译。
- 拆分模型，仅编译下游 Conformer/分类头，WavLM 保留 CPU 或其他执行路径。
- 尝试不同 Pulsar2 版本或 tile/slice 配置。
- 改写 attention 导出图，规避当前 Gather pattern。

## 4s 复测

按用户确认将输入窗口缩短到 4 秒后重新导出：

- Input: `[1, 1, 64000]`
- Output: `[1, 199, 11]`
- ONNX vs PyTorch cosine: `0.9999999999988147`
- Pulsar2 quantization: 完成
- NPU backend: 仍失败于 `/layers.0/attention/Gather_1`

失败张量从 `(1,16,799,799)` 降为 `(1,16,199,199)`，但 backend Gather tiler 仍无法处理该 pattern。因此下一步应优先考虑模型拆分或 attention 图改写，而不是只继续缩短窗口。
