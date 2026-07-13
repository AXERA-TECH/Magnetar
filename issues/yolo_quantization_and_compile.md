# Per-Tensor 量化中小值通道被压为 0 的根因与解决方案

## 现象

ONNX 输出 tensor 包含多个语义通道（如 YOLOv8-seg 的 output0 含 bbox + obj_conf + cls_scores + mask_coeffs），
通道间值域差异巨大（bbox: 0-640, obj_conf: 0-0.006, cls: 0-0.96, mask: -5-3）。
Pulsar2 per-tensor U8 量化后，obj_conf 和 cls 通道全部变成 0，导致检测完全失效。

**已确认非 pyaxengine/ax_run_model 问题** ——两者输出完全一致，问题发生在编译阶段的量化。

## 根因分析

Pulsar2 对每个输出 tensor 使用 **per-tensor**（非 per-channel）U8 量化：

```
U8_scale = max_across_all_channels / 255
         = 640 / 255 ≈ 2.5
```

obj_conf 最大值仅 0.006，U8 量化值 = 0.006 / 2.5 = 0.0024 → 取整为 0 → dequant = 0。
即使设为 U16，obj_conf = 0.006 / (640/65535) = 0.61 → 取整为 0。

**本质：17-bit 动态范围需求 vs 8/16-bit 量化器的不匹配。**

## 无效方案（已验证）

| 方案 | 结果 | 原因 |
|------|------|------|
| 输出端加 `Mul(×1000)` | Pulsar2 常量折叠消除 | 图优化 pass 识别并移除常数乘法 |
| `layer_configs` 指定 `end_tensor_names` | 只保护最后一层，上游仍被 U8 量化 | per-tensor scale 在上游 Conv 输出层已确定 |
| 拆分 ONNX 为多输出 + `Split` 节点 | Pulsar2 内部不独立量化 Split 各输出 | Split 输出共用输入 tensor 的量化参数 |
| 删除 `Sigmoid` 用 raw logits | 值域扩大但仍有偏移 | 不对称 U8 量化的 zero_point 偏移未校准 |
| `op_types + end_tensor_names` 设 FP32 | 不生效 | Pulsar2 内部层名与 ONNX 不同；FP32 设置只在最后一级生效 |
| 全模型 U16 | obj_conf 仍为 0 | bbox 主导的 per-tensor scale 下 U16 也不够 |
| `enable_smooth_quant` | 编译卡死 | 内存/计算量过大 |
| `enable_easy_quant` | 编译卡死 | 同上 |
| `calibration_method: Percentile/KL` | 无改善 | 不改变 per-tensor 量化本质 |
| `std:[1,1,1]` 跳过 pre_norm | 校准失效 | 校准图未经归一化，激活值域完全错误 |

## 有效方案

### 绕过 Sigmoid + 正确输入预处理

**原理：** Sigmoid 输出值域 [0,1] 在 per-tensor 量化中极易被 bbox(0-640) 压为 0。
将 Sigmoid 从 ONNX 图中删除，让 raw logits（值域[-100, 3]）直接进入输出 Concat。
raw logits 的绝对值足够大，在 [-105, 637] 的整体值域中不会被量化成 0。

**ONNX 修改：**
1. 定位最终 Concat 节点的 cls/conf 分支输入（`Sigmoid_output`）
2. 替换为 Sigmoid 的输入（`Concat_1_output`，即 raw logits）
3. 删除 Sigmoid 节点
4. `onnx.checker.check_model()` 验证

**后处理补偿：**
```python
obj_conf = sigmoid(det[4])       # ch4: raw logit → [0,1]
cls_scores = sigmoid(det[5:9])   # ch5-8: raw logits → [0,1]
score = obj_conf * cls_scores.max(axis=1)
```

**输入格式：**
- 模型内置 pre_norm（std:[255,255,255]），自动 ÷255
- 运行时输入：float32 [0,255] NCHW（pre_norm 还原为 [0,1]）
- 不要设 `std:[1,1,1]`——跳过 pre_norm 会导致校准阶段数据未归一化

**验证结果：**
- 板端检出 7-8 objects，bbox 与 PC ONNX 基准高度一致
- 推理延迟：2.1ms (NPU3)
- obj_conf 通道有轻微量化偏差，但 cls_max 单独做 score 足够检出

## 通用知识

1. **per-tensor 量化的致命弱点：** 当单一 tensor 包含多个语义通道且值域跨数量级时，
   小值通道必然被量化为 0。量化比特数（U8/U16）不能解决此问题——需要的是独立的 scale。

2. **ONNX 图级绕过优于 Pulsar2 配置：** `layer_configs`/`end_tensor_names` 对 Pulsar2
   内部图优化无控制力。在 ONNX 层面重构数据流（删除/重连节点）是唯一可控手段。

3. **激活函数是量化瓶颈：** Sigmoid/Softmax 将任意范围映射到 [0,1] 或概率分布，
   削弱了量化鲁棒性。将其移到后处理（CPU 上完成）可同时解决量化和精度问题。

4. **输入预处理不可跳过编译时配置：** `std:[1,1,1]` 虽然跳过运行时 pre_norm，
   但校准阶段也跳过归一化，导致激活统计完全错误。正确的做法是保留
   `std:[255,255,255]` 编译，运行时喂 [0,255] 数据。

5. **拆分输出优于 Scale 技巧：** 在 ONNX 中添加 `Mul(×scale)` 会被 Pulsar2 图优化折叠。
   将多通道 tensor 拆成独立输出节点（独立 Concat，非 Split）可实现独立量化，
   但需确保每条分支有独立计算路径不被共享层复用。

6. **AX650 无 FP16：** DataType 枚举中 FP16=9 不可用，应使用 FP32=10 或 U16=3。

7. **校准方法是次要因素：** MinMax/Percentile/KL/MSE 在校准集覆盖充分时差异不大，
   不能替代 per-tensor → per-channel 的架构级改进。

## 相关文件

- 原始 ONNX: `export/model.onnx`
- 修改后 ONNX: `export/model_bypass_sig.onnx`
- 最终模型: `compile/npu3_kl/model`
- 交付包: `package/`
# YOLO26m Pulsar2 编译: Mod 算子不支持

## 现象

ONNX 模型含 `Mod(fmod=0)` 算子，Pulsar2 编译时报错:
```
KeyError: 'op Mod attr fmod does not exist'
```

## 根因

YOLO26m ONNX 导出使用 `TopK` + `Mod` 计算索引偏移（`TopK_indices % 2`）。Pulsar2 6.0 的 ONNX 解析器不支持 `Mod` 算子。

## 解决方案

ONNX 图改写，将 `Mod(a, b)` 替换为等效运算:
```
Cast(a, float) → Div(float, float) → Floor → Mul(float, float) → Sub(float, float) → Cast(int64)
```

等价于: `a - b * floor(a / b)`

需注意:
- TopK 输出为 int64，需 Cast 为 float 后参与浮点运算
- 常数 b 为 int64 initializer，需额外创建 float 版本避免 Div 类型不匹配

## 相关文件

- 原始 ONNX: export/model.onnx
- 修改脚本: export/fix_mod.py
