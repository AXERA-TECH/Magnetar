# PiperTTS 中文 AX650 转换经验总结

> 任务: PiperTTS zh_CN huayan-medium → AX650 NPU  
> 最终方案: CPU Encoder + NPU 合并模型 (FD+HG)，RTF=0.35  
> 交付包: [inoryQwQ/piper-tts-ax650-zh](https://huggingface.co/inoryQwQ/piper-tts-ax650-zh)

---

## 1. 双模型共存问题 🔴

### 现象
两个 axmodel（Flow Decoder + HiFi-GAN）在同一进程加载时，第二个报 `RuntimeError: Failed to load model.`，无详细错误。

### 根因
- Python axengine 0.1.3 的 `SessionOptions` 为空，`provider_options` 无效
- 无法给每个模型分配独立 NPU 核心
- 所有 provider_options 参数（core_id/vnpu/affinity/device_id）均被忽略

### 解决
**合并为单一 ONNX → 单一 AXMODEL。** 将 Flow Decoder 的输出直接连到 HiFi-GAN 的输入，中间插入 `Clip(-8, 8)` 节点（FD 输出范围 [-8,8]，HG 需要 clip）。

```python
# 合并要点
- FD 输出名 "mel" [1,192,500] → HG 输入名 "decoder_input" [1,192,500]
- 插入 Clip 节点: clip(mel, -8, 8)
- 重命名 HG 内部所有 decoder_input 引用 → mel_clipped
```

合并后模型 10.3MB，单次推理 52ms，无任何加载冲突。

### 通用建议
- 在编译前就考虑合并 pipeline 内的连续 subgraph
- Whisper/SATRN 等"成功"案例可能用了不同的芯片/编译配置，不一定可复用

---

## 2. Encoder 量化——Transformer 的 Softmax 瓶颈 🔴

### 现象
所有 PTQ 方法（INT8/U16/SmoothQuant/Brecq/Percentile/TransformerOpt2/LSQ）的最高 cosine 只有 **0.78**。

### 根因
6 层 Transformer Encoder 的 Self-Attention 路径：
```
Softmax(Q·K^T / √d) → MatMul(Attention · V)
```
- Softmax 输出在 [0, 1] 高度稀疏，INT8 只有 256 级
- `Equal → Where` 构成的 causal mask 在量化后产生 1-bit 误差
- 6 层累积后崩掉

### QAT 尝试
- 权重 QAT (INT8 per-channel): PyTorch cos=**1.000**
- 权重+激活 QAT (U16 activation): PyTorch cos=**1.000**  
- Pulsar2 编译后: NPU cos 退化到 0.57-0.78

**结论: QAT 训练的量化方案和 Pulsar2 的 PTQ 方案不兼容**——Pulsar2 重新计算 scale 导致收益归零。

### QDQ 尝试（正确方向）
- onnxruntime QDQ ONNX (仅 Conv/MatMul): ONNX 层面 cos=**0.993**
- Pulsar2 量化阶段: "AX Load QDQ Config Pass" 正确识别 QDQ 参数 ✅
- Pulsar2 导出阶段: ❌ `AssertionError: tensor round only takes effect on torch tensor.`
- 已向爱芯提 issue: [Pulsar2#3](https://hf-mirror.com/AXERA-TECH/Pulsar2/discussions/3)

### 建议
1. **音频类 Transformer Encoder 果断留 CPU**，不要浪费精力在 NPU 量化上
2. 如果必须上 NPU，走 QAT→QDQ ONNX 通道，绕开 Pulsar2 PTQ
3. 关注 Pulsar2 的 QuantONNX 导出修复进展

---

## 3. 校准数据格式 ✅

### 多输入模型
Pulsar2 支持多输入校准，每个输入独立 `tar.gz`:
```json
"input_configs": [
  { "tensor_name": "z_p",   "calibration_dataset": "/workspace/.../z_p.tar.gz" },
  { "tensor_name": "mask",  "calibration_dataset": "/workspace/.../mask.tar.gz" }
]
```
- 格式: `tar.gz` 内包含 `.npy` 文件
- `calibration_format`: "Numpy"
- `calibration_size`: 8 (建议 4-32)

### 数据生成
用原始 ONNX 跑推理采集中间特征:
```python
sess = ort.InferenceSession(full_model.onnx)
z_p, mask = sess.run(None, {input: ...})
np.save("z_p_0000.npy", z_p)
```

---

## 4. 编译配置选型 ✅

### Flow Decoder + HiFi-GAN
```json
{
  "quant": {
    "calibration_method": "MinMax",
    "enable_smooth_quant": true,
    "smooth_quant_threshold": 0.5,
    "layer_configs": [
      { "op_type": "Conv", "data_type": "U16", "weight_data_type": "S8", "output_data_type": "U16" }
    ]
  }
}
```
- U16 激活 + S8 权重: cosine **0.987**（比纯 INT8 高 ~0.05）
- NPU3 模式（3 核），编译 28.5 GMACs

### HiFi-GAN
- INT8 KL 即可达到 cosine **0.995**（vocoder 对量化不敏感）

---

## 5. ONNX 操作经验

### onnx2torch 权重复制
```python
# ONNX initializer → PyTorch state_dict
init_data = {i.name: numpy_helper.to_array(i) for i in onnx_model.graph.initializer}
mapping = {name.lstrip("enc_p."): name for name in init_data if "enc_p." in name}
```

### QAT 权重回写 ONNX
onnx2torch FX graph 无法直接 `torch.onnx.export()`（torch.export 兼容性），改用手动回写:
```python
for init in orig_onnx.graph.initializer:
    if init.name in qat_weights:
        new_tensor = numpy_helper.from_array(qat_weights[init.name], name=init.name)
        init.CopyFrom(new_tensor)
```

---

## 6. 板端 Python SDK 使用

```python
import axengine as axe
# 单模型加载（推荐）
s = axe.InferenceSession("model.axmodel", providers=["AxEngineExecutionProvider"])
inputs = {s.get_inputs()[0].name: np.ascontiguousarray(data)}
output = s.run(None, inputs)[0]
del s  # 显式释放
```

关键点:
- 输入必须是 `np.ascontiguousarray`（C-contiguous）
- `get_inputs()[0].name` 而非硬编码输入名（不同编译可能变化）
- 用完后 `del` 释放（axengine 0.1.3 无 `close()`）

---

## 7. 定长分段合成

PiperTTS 输出长度取决于文本长度。NPU 模型固定 shape [500 mel frames]。

```python
MEL_FRAMES_MAX = 500
for s in range(0, T, MEL_FRAMES_MAX):
    e = min(s + MEL_FRAMES_MAX, T)
    z = np.pad(z_p[:,:,s:e], ((0,0),(0,0),(0,MEL_FRAMES_MAX-(e-s))))
    # ... 推理
    chunks.append(audio[: (e-s)*256])  # 256 = hop_length
audio = np.concatenate(chunks)[:audio_len]
```

---

## 8. 关键文件路径

| 文件 | 用途 |
|------|------|
| `export/flow_decoder_static.onnx` | FD 静态 shape ONNX |
| `export/hifigan_decoder.onnx` | HG ONNX |
| `export/piper_tts_merged.onnx` | 合并 ONNX (FD+Clip+HG) |
| `export/encoder_v2_sim.onnx` | Encoder ONNX |
| `export/qat_encoder_v3.py` | Encoder QAT 训练脚本 |
| `export/qat_encoder_output/encoder_qat_v3_u16.onnx` | QAT 权重 ONNX |
| `export/build_qdq_v2.py` | QDQ ONNX 构建脚本 |
| `export/qat_encoder_output/encoder_qdq_ort.onnx` | QDQ ONNX (cos=0.993) |
| `compile/merged_u16_mm_sq` | 最终合并模型编译目录 |
| `package/` | 交付包 |

---

## 教训速查

| 问题 | 一句话 |
|------|--------|
| 双模型加载失败 | 合并 ONNX → 单一 AXMODEL |
| Encoder 量化不达标 | Softmax 是死结，留 CPU |
| QAT 训练好但编译后退化 | Pulsar2 PTQ 与 QAT 方案不兼容，等 QDQ 修复 |
| onnx2torch 导出失败 | 手动回写权重到 ONNX protobuf |
| 多输入校准数据 | 每个输入独立 tar.gz |
| Pulsar2 配置记不住 | `python magnetar/pulsar2_ref.py` |
