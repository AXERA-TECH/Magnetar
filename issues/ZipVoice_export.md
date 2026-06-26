# ZipVoice EXPORT 阶段 ONNX 导出与改写问题

ZipVoice `fm_decoder` 从动态 ONNX 到可被 Pulsar2 5.1 接受的静态 ONNX，经历多轮改写。

---

## [007] PyTorch 2.10 dynamic_axes 导出失败

**问题**：官方 `zipvoice.bin.onnx_export` 在 PyTorch 2.10 下失败：

```text
RuntimeError: Failed to convert 'dynamic_axes' to 'dynamic_shapes'.
```

**根因**：PyTorch 2.9+ 的 `torch.onnx.export` 默认走新版导出路径，旧式 `dynamic_axes` 不兼容。

**解决**：自实现导出脚本，显式指定 `dynamo=False`：

```python
torch.onnx.export(model, args, path, dynamo=False, dynamic_axes=...)
```

---

## [008] ONNX Runtime 1.24 静态图加载失败

**问题**：ONNX checker 通过，但 ORT 1.24.1 加载时触发两类错误：
- `text_encoder`：external-data 相关加载异常（文件实际无 external initializer）。
- `fm_decoder`：`ORT_ENABLE_BASIC` 触发 `Expand` shape inference 错误。

**解决**：
- 验证环境固定为 ORT 1.22.1。
- 创建 ORT Session 时设置 `graph_optimization_level = ORT_DISABLE_ALL`。

**经验**：Zipformer 类模型的 traced ONNX 对 ORT 版本和优化级别敏感，导出验证须记录两者。

---

## [009] Pulsar2 5.1 scalar 输入和 Expand shape inference 失败

**问题**：`fm_decoder_static.onnx` 含 scalar 输入 `t`/`guidance_scale`，Pulsar2 5.1 编译失败：

```text
IndexError('list index out of range')  # scalar 校准数据
ShapeInferenceError: Incompatible dimensions  # Expand
```

**根因**：
- Pulsar2 5.1 量化校准不稳定支持 shape `()` 的 scalar 输入。
- Pulsar2 内部强制 onnxsim，触发 Expand 维度不兼容（ORT 关闭优化后可运行但 Pulsar2 不行）。

**解决**：
1. EXPORT 时将 scalar 改为 rank-1：外部输入 `t: [1]`/`guidance_scale: [1]`，图内用 `Squeeze` 转回 scalar。
2. 静态化位置编码（见 [010]）消除 Expand 问题。

**经验**：Pulsar2 5.1 编译前应避免 scalar 外部输入；位置编码 `Expand` 即使 ONNX checker 通过，也需额外验证 Pulsar2 onnxsim 兼容性。

---

## [010] 静态化位置编码避免 If/Expand shape inference

**问题**：`fm_decoder` 中 `CompactRelPositionalEncoding.extend_pe()` 导出的 `If:else_branch` 含 `arange/sign/log/atan/cos/sin/scatter/expand`，Pulsar2 5.1 编译时 `Expand` 报 shape inference 不兼容。

**根因**：该分支用于位置编码缓存不足时重新生成 `pe`，但静态导出时 `max_len=1000` 已足够覆盖所有序列长度，分支实际不需要保留。

**修复**：导出时 monkeypatch `CompactRelPositionalEncoding.forward()`，直接用已有 `self.pe` 切片，跳过 `extend_pe()` 和 dropout：

```python
def forward_static(self, x, ...):
    pos_emb = self.pe[0, :x.size(0)].unsqueeze(0)
    return self.dropout(x), pos_emb  # dropout is identity at eval
```

**效果**：`If=0`，`Expand=24`（原 `If=5`，`Expand=69`）；Torch/ONNX cosine `0.9999999999959933`。

**注意**：依赖 `max_len` 覆盖全部层中最大时间长度，更换导出序列长度时需重新确认。

---

## [011] SimpleDownsample 零长度 Expand 导致编译失败

**问题**：解决位置编码后，编译仍失败：

```text
op name: /fm/fm_decoder/1/downsample/Expand, illegal value_info r: [0, 2, 512]
```

**根因**：`SimpleDownsample` 将输入 pad 到 downsample factor 整数倍。当 `seq_len=256` 且 factor 为 2/4/2 时，`pad=0`，PyTorch trace 仍保留 `Expand` 到 `[0, batch, channels]` 的分支。ORT 可运行，Pulsar2 不接受零维输出 shape。

**修复**：导出时 monkeypatch `SimpleDownsample.forward()`，静态检测 `pad == 0` 时跳过 expand+cat：

```python
def forward_static(self, src):
    pad = d_seq_len * ds - seq_len
    if pad == 0:
        return src.reshape(d_seq_len, ds, batch, channels).sum(1) * weight
    # else: original logic
```

**验证**：ONNX 图中不再含 `/downsample/Expand`；ORT + Pulsar2 均通过；Torch/ONNX 对分保持一致。
