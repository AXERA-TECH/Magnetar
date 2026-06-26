# ZipVoice COMPILE 与精度调试问题汇总

ZipVoice `fm_decoder` 编译阶段按顺序遭遇多个算子不支持问题，之后进入漫长的精度调试。

---

## [012] Pulsar2 5.1 Log AXIR export 失败

**问题**：量化完成后，AXIR export 阶段失败：

```text
Operator(name:.../Log, type:Log) convert error:
property 'attributes' of 'Operation' object has no setter
```

**根因**：Swoosh 激活含 `logaddexp/softplus` 导出的 `Log` 算子，Pulsar2 5.1 float `Log` 的 AXIR exporter 内部属性 setter 错误。

**修复**：导出时加 `--no-log-swoosh-export`，将 SwooshL/R 替换为 sigmoid-based 近似：
- SwooshL: `(x - 4) * sigmoid(x - 4) - 0.08*x - 0.035`
- SwooshR: `(x - 1) * sigmoid(x - 1) - 0.08*x - 0.313261687`

修复后：`Log=0`，Torch/ONNX cosine `0.9999999988`。

---

## [013] BiasNorm `Pow(power=-0.5)` 不支持

**问题**：no-log 版本编译时报：

```text
AxPow only supports power with 0.25, 0.5, 2 and 4, got [-0.5]
```

**根因**：`BiasNorm.forward()` 导出 `** -0.5` 即 `Pow(power=-0.5)`，AX650 backend 不支持负指数。

**修复**：monkeypatch `BiasNorm.forward()` 改写为 `Sqrt + Div`：

```python
mean_square = torch.mean((x - bias) * (x - bias), dim=channel_dim, keepdim=True)
rms = torch.sqrt(mean_square + 1.0e-12)
return (x / rms) * self.log_scale.exp()
```

注意：初版改写用 `1.0 / torch.sqrt(...)` 会生成 `Reciprocal`，同样不被支持（见 [014]）。

修复后：`Pow=0`，`Sqrt=16`，`Div=65`，Torch/ONNX cosine `0.9999999975`，Pulsar2 编译通过，生成 `zipvoice_fm_decoder_no_log_no_neg_pow_div_u16.axmodel`（142MB，NPU subgraph 单一）。

---

## [014] Reciprocal 不支持

**根因**：`1.0 / torch.sqrt(...)` 导出为 `Reciprocal`，Pulsar2 5.1 同样不支持。

**修复**：直接写成除法 `x / rms`（见 [013] 最终版本）。

---

## [015] SIMULATE fm_decoder quant 精度严重不达标

**问题**：编译成功的 AXMODEL 与 ONNX 对比：
- all-U16：cosine `0.3083`，MAE `0.789`
- all-S16/all-FP32 均无改善

**已排除**：ONNX 与 Pulsar2 float debug 输出 cosine `0.9999999916`，说明不是导出问题；输入喂入格式已确认正确。

**发现**：partial-U16 配置漏覆盖 `Concat/Tile/Transpose/Slice/GatherElements` 等 op，导致"名义 U16 实际大量 U8"；全覆盖后精度仅小幅改善，说明是整体路径问题。

**后续方向**：使用 precision_analysis 定位首次发散层（见 [016][017]）。

---

## [016] all-layers FP32 precision analysis 仍发散

**问题**：将所有 dispatching layer 设为 FP32，EndToEnd PA 仍只有 cosine `0.50449`，与以下配置无关：
- `transformer_opt_level=1/0`，smooth quant 开/关，`disable_quant_optimization=true`

```text
ORT vs PA float cosine:      0.9999999789
ORT vs PA quant/xrun cosine: 0.5039
```

**结论**：发散来自 Pulsar2 EndToEnd/xrun 路径本身，不是解析或参考输出问题。Pulsar2 5.1 对该模型的 precision analysis upper bound 约为 0.50。

首次明显发散窗口在 `conv_module2/depthwise_conv` 附近，`Slice` 输出数值范围达数百，经 sigmoid 饱和区放大后通过门控乘法累积。

**后续**：需在 EXPORT 阶段修改部署图数值路径（见 [017]）。

---

## [017] 线性层改写为 1x1 Conv 后 precision analysis 达到 1.0

**问题**：即使设置 `data_type=FP32`/`output_data_type=FP32`/`weight_data_type=FP32`，`quant_axmodel.json` 仍显示 `Gemm`/`MatMul` 权重为 8-bit `BAKED`，PA cosine 卡在 0.50-0.56。

**根因**：Pulsar2 5.1 中 `weight_data_type=FP32` 对 Conv 有效，但不能让 Gemm/MatMul 权重保持 FP32。

**解决**：EXPORT 阶段将所有 `torch.nn.Linear` 改写为 `reshape → Conv1d(kernel=1) → reshape`：

```python
def linear_as_conv(x, weight, bias):
    B, T, C = x.shape
    x = x.reshape(B, C, T)
    x = F.conv1d(x, weight.unsqueeze(-1), bias)
    return x.transpose(1, 2)
```

导出结果：`Gemm=0`，`Conv=329`，`MatMul=80`，Torch/ONNX cosine `0.9999999990`。

PA 结果：final `v` cosine `1.0`，`Num of Quantized Op: 0`。

**经验**：验证权重实际状态应看 `quant_axmodel.json`，而不只看 PA 表的 `FP32->FP32` 标注。

---

## [018] fm_decoder 编译 silent hang（250B MACs 超大模型）

**问题**：`work_part1_trial3` 编译完成 `calc input dependencies` 后，静默超过 1h45min 无任何日志输出。

**模型规模**：250B MACs，tiling op 4643，build op 7793，dependencies 项 827,735。

| 已完成阶段 | 耗时 |
|-----------|------|
| tiling op | 22min |
| build op serially | 20min |
| calc input dependencies | 14min |
| **之后（内部调度/代码生成）** | **>1h45min，无输出** |

**结论**：容器未崩溃，但静默无法区分"慢速运行"和"卡死"。250B MACs 级别模型超出当前 Pulsar2 版本可编译范围。

**建议**：模型分割（沿 Stage2→Stage3 边界拆为两个子模型）或降低量化精度后重试。
