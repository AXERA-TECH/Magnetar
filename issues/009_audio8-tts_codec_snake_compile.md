# Audio8-TTS-Preview-0.6b codec Snake 编译问题

## 现象

`codec_encoder` / `codec_decoder` 在 Pulsar2 7.0-lite（AX650, NPU3）编译时于
NPU 后端 tile 阶段报错：

```
TileFailException: AxQuantizedSnake, AxSin builder or naive_builder should be set
  op: op_...:AxQuantizedSnake
```

把 Snake/Sin/Pow 等通过 `layer_configs` 全部强制 FP32 后变为：

```
TileFailException: AxSnake, AxSin builder or naive_builder should be set
  op: op_...:AxSnake  attrs: {'output_dtype': 'FP32'}
```

即 7.0-lite 的 AX650 NPU 后端**既没有量化 Snake builder，也没有 FP32 Snake
builder**（Sin 有 AxSin/naive builder，但融合后的 AxSnake 没有）。

## 根因

Pulsar2 前端图优化会把 ArkttsSnake1d 的
`x + (1/(alpha+eps)) * sin(alpha*x)^2` 模式融合为单个 `Snake` 算子
（`optimized.onnx` 中 29 个 `Snake` 节点）；后端缺该算子实现导致 tile 失败。

## 解决

对 codec 两个子模型在 `pulsar2_config.json` 中设置：

```json
"onnx_opt": {
  "disable_onnx_optimization": true,
  "enable_onnxsim": false,
  "model_check": false,
  "disable_transformation_check": true
}
```

导出 ONNX 本身不含 Snake（只有 Sin/Pow/Mul/Add），禁用前端优化即可避免融合；
这些基础算子均有后端实现。同时 `layer_configs` 保持 Sin/Pow/Conv/MatMul 等全
FP32（7.0-lite 的量化 Snake/Sin builder 缺失），`compiler.check` 对离散
`codes` 输出关闭（改由 SIMULATE exact_match 验证）。

## 备注

codec_encoder 输出为离散码本索引（int64→int32），编译期余弦对分无意义；
codec_decoder 输出为连续音频，保留 `compiler.check: 3`（cosine ≥ 0.99）。
