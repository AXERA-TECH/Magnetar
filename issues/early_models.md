# 早期模型常见问题：MobileNetV2 / ResNet18 / YOLOv5s

---

## [000] MobileNetV2 EXPORT 精度指标误用

**问题**：量化模型输出最大相对差异达 28x，余弦相似度 0.995，Top-k 完全正确。

**根因**：
- 相对差异不适用于输出含接近零值的场景（分母趋零放大误差）。
- 违规配置 `highest_mix_precision: true`。
- 校准数据与 `input_processors` 归一化参数不一致（ImageNet 归一化 vs mean=[0,0,0]）。

**解决**：
- 移除 `highest_mix_precision: true`。
- 修正 `input_processors.mean/std` 与校准数据保持一致。
- 弃用相对差异指标，改用余弦相似度 + Top-k 匹配率。

**推荐评估指标**：

| 指标 | 阈值 |
|------|------|
| 余弦相似度 | >0.99 |
| Top-1 匹配率 | 100% |
| Top-5 匹配率 | 100% |

---

## [001] ResNet18 SIMULATE 精度严重不达标

**问题**：仿真 cosine 0.687，MSE 1.163，Top-5 overlap 1/5。

**根因**：`src_dtype` 配置为 `U8`，但 ONNX 模型已包含归一化预处理，期望 FP32 输入（范围约 -2~2）。U8 输入被 dequantize 处理为 0-255 范围，导致归一化层接收错误数据。

**解决**：将 `input_processors.src_dtype` 改为 `FP32`。修复后 cosine 0.998，MSE 0.027，Top-5 overlap 4/5。

```json
"input_processors": [{"tensor_name": "input", "src_dtype": "FP32", "mean": [], "std": []}]
```

**经验**：ONNX 若已包含完整预处理链，`src_dtype` 必须为 `FP32`；若模型不含归一化，则配置 `mean`/`std` 由工具链执行。

---

## [002] YOLOv5s COMPILE Pulsar2 6.0 配置字段差异

**问题**：Pulsar2 6.0 编译失败，报 `has no field named "dst_format"` 和 `input(images) doesn't exist`。

**根因**：
- Pulsar2 6.0 `InputProcessor` 字段为 `tensor_format`/`src_format`/`src_dtype`，不支持旧字段 `dst_format`/`dst_layout`。
- 量化校准必须用 `quant.input_configs`，不等价于 `quant.input_sample_dir`。

**解决**：使用正确字段形态：

```json
{
  "quant": {
    "input_configs": [{
      "tensor_name": "images",
      "calibration_dataset": "calib_data/images.tar.gz",
      "calibration_format": "Numpy",
      "calibration_size": -1
    }]
  },
  "input_processors": [{
    "tensor_name": "images",
    "tensor_format": "RGB",
    "tensor_layout": "NCHW",
    "src_format": "RGB",
    "src_dtype": "FP32",
    "src_layout": "NCHW"
  }]
}
```

**经验**：遇到配置字段问题，优先读取镜像内 `/opt/pulsar2/yamain/config/build_config.proto`。
