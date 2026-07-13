# [017] kokoro COMPILE 失败：Pulsar2/PPQ 不支持 SequenceEmpty

## 现象

Kokoro TTS 完整 ONNX 使用 Pulsar2 6.0 编译到 AX650/NPU3 时失败。

第二次编译在关闭 ONNX 优化后进入量化阶段，但 PPQ 执行图时报：

```text
NotImplementedError: Graph op: /SequenceEmpty(SequenceEmpty) has no backend implementation on target platform TargetPlatform.UNSPECIFIED
RuntimeError: Op Execution Error: /SequenceEmpty(TargetPlatform.UNSPECIFIED)
yamain.common.error.CodeException: (<ErrorCode.QuantError: 3>, ...)
```

## 环境

- 模型：Kokoro TTS `hexgrad/Kokoro-82M`
- ONNX：opset 17，静态输入输出 shape
- Pulsar2：Docker `pulsar2:6.0-lite`
- Pulsar2 version：`6.0`
- commit：`48520c11`
- 目标：`AX650`
- npu_mode：`NPU3`

## 已确认不是的问题

- 校准数据不是随机数据，来自真实文本 token ids、`af_heart` voice style 和 speed。
- `input_ids` 校准数据 dtype 为 `int64`，`input_processors.src_dtype` 为 `S64`。
- `style` 和 `speed` 校准数据 dtype 为 `float32`，`input_processors.src_dtype` 为 `FP32`。
- 未开启 `highest_mix_precision`，配置中为 `false`。

## 根因判断

完整 TTS ONNX 图中包含 ONNX Sequence/control-flow 相关节点：

- `SequenceEmpty`
- `SequenceInsert`
- `SequenceAt`
- `SplitToSequence`
- `ConcatFromSequence`

Pulsar2/PPQ 量化执行器没有 `SequenceEmpty` 后端实现，因此无法完成 quant tracing。

## 可选修复方向

1. 改写导出 forward，避免 `pack_padded_sequence`、Sequence 和动态序列构造进入 ONNX 图。
2. 将 Kokoro 切分为多个子图，CPU 侧处理 duration/alignment，再分别编译可支持的 encoder/decoder 子图。
3. 将 `repeat_interleave`/alignment 逻辑改成固定 shape 的张量算子，再重新 EXPORT 并对分。

## 状态

未解决。当前流程在 COMPILE 阶段 STOP，需确认下一步导出/切分策略。
# Kokoro COMPILE decoder/vocoder 图改写

## 背景

Kokoro 完整图在 Pulsar2 中因 `SequenceEmpty` 无后端实现无法编译。切分到 decoder/vocoder 后，又遇到多类 ONNX/Pulsar2/AX650 后端限制。

## 现象

- decoder/vocoder 中随机激励会导出随机相关算子，不适合作为可复现静态 AXMODEL。
- `Pad`、`Atan`、`ConstantOfShape`、`Reciprocal`、动态 `Slice` 边界在 PPQ 或 AXIR export 中失败。
- 单体 decoder 子图虽可进入 NPU backend，但 `f0_upsamp` 产生 `Resize` 到 `84600`，AX650 后端报 `integer 84599 does not fit uint16_t`。

## 处理

- 在任务目录导出 wrapper 中确定化随机源，避免修改原始 `origin/`。
- 折叠 `Shape/Gather`、AdaIN `Slice` 边界、initializer `Identity`、`ConstantOfShape` 和常量 `Reciprocal`。
- 将 STFT center pad 改写为 Conv padding，末端左补零改写为 Slice/Concat。
- 将 harmonic source/STFT 作为 CPU glue 生成 `har [1,22,16921]`，把 decoder/vocoder 二级切分为：
  - `decoder_pre`: `asr,f0,n,style -> x`
  - `generator`: `x,har,style -> waveform`

## 结果

最终生成并编译通过：

- `compile/split_f0ntrain/kokoro_f0ntrain.axmodel`
- `compile/split_decoder_pre/kokoro_decoder_pre.axmodel`
- `compile/split_generator/kokoro_generator.axmodel`

后续 SDK 和 PACKAGE 必须保留 CPU alignment/har glue，并按该 5 子图拓扑执行。
# Kokoro RUNONBOARD BERT 混合 U16 后端输出异常

## 背景

- 模型：Kokoro TTS
- 目标：AX650 / `npu_mode=NPU3`
- 子图：`bert_encoder`
- 实验配置：`compile/split_bert_encoder_compute_u16/pulsar2_config_bert_encoder_compute_u16.json`
- 主要配置：`MatMul/Add/LayerNormalization/Mul/Pow/Softmax/Tanh` 设置 `data_type=U16`，未启用 `highest_mix_precision`

## 现象

量化 debug 输出显示修复有效：

- ONNX vs quant debug cosine：`0.9994577859`
- MAE：`0.0301595174`
- max abs diff：`0.1570585370`

但后端执行输出崩坏：

- ONNX vs `pulsar2 run` cosine：`0.0102717679`
- ONNX vs AX650C `ax_run_model` cosine：`0.0102717679`
- AX650C board vs `pulsar2 run` cosine：`1.0`

原始 INT8 BERT 作为对照：

- ONNX vs `pulsar2 run` cosine：`0.9501246568`
- ONNX vs AX650C `ax_run_model` cosine：`0.9501246568`
- AX650C board vs `pulsar2 run` cosine：`1.0`

## 结论

该问题不是 `pulsar2 run` simulator 独有误差；真实 AX650C 板端输出与 simulator 完全一致。`work/quant/debug/io` 的 quant debug 通过不能作为 AXMODEL 后端执行通过依据。

## 排查记录

- 板子：`10.126.35.203`，hostname `pyramid-openclaw`，`AX650C_CHIP`
- BERT compute U16 板端 latency：`12.263 ms`
- 原始 INT8 BERT 板端 latency：`4.150 ms`
- `--vnpu/--affinity`：
  - `-v 0 -a 1` 可运行
  - `-v 1` / `-v 2` 报 3 Core 模型与 visual NPU mode 不匹配
  - `-v 3` 加载失败
  - `-v 0 -a 7` affinity 非法

## 建议

- 不采用 BERT compute U16 AXMODEL 作为交付修复。
- 后续修复需要更细切分 BERT 或尝试 S16/更窄 U16 边界，并以 `pulsar2 run` 或真实板端输出作为通过条件。
- 对 transformer 子图不能只依据 quant debug 判断精度。
# Kokoro RUNONBOARD input_ids runtime dtype 为 int32

## 现象

Python SDK 首次在 AX650C 板端通过 `pyaxengine` 运行 BERT 子图时失败：

```text
model inputs(input_ids) expect shape [1, 54] and dtype int32,
however gets input with shape (1, 54) and dtype int64
```

ONNX metadata 中 `input_ids` 为 `int64`，但 Pulsar2 编译后的 AXMODEL runtime IO 为 `int32`。此前 `pulsar2 run` raw 输入也需要按 4 字节整数写入。

## 修复

Python SDK 保持 API 层接受 `int64` token ids，但在喂给 `axengine.InferenceSession` 前转换为 `int32`：

```python
ax_input_ids = input_ids.astype(np.int32)
```

同一修复用于 `bert_encoder` 与 `postbert` 子图的 `input_ids` feed。

## 结果

修复后板端 Python SDK 示例使用 `AxEngineExecutionProvider` 完整运行 5 个 AXMODEL，生成 `84600` samples 的 wav 输出。
# Kokoro generator NPUBackend PA cmodel shape mismatch

## 现象

对 `kokoro_generator` 全图 U16 配置执行 Pulsar2 precision analysis：

- `precision_analysis_method=EndToEnd`
- `precision_analysis_mode=NPUBackend`
- `highest_mix_precision=false`

配置路径：

`todos/work/20260702-135222-kokoro/compile/split_generator_u16_pa_npubackend_rerun/pulsar2_config_generator_u16_pa_npubackend.json`

日志路径：

`todos/work/20260702-135222-kokoro/compile/split_generator_u16_pa_npubackend_rerun/compile_generator_u16_pa_npubackend.log`

量化完成并进入 native backend xrun，尾部已导出 `_Exp_output_0.npy`、`_Sin_output_0.npy`、`_Cos_output_0.npy`、`_Mul_output_0.npy`、`_Mul_1_output_0.npy`，随后 AX650 cmodel abort：

```text
terminate called after throwing an instance of 'std::runtime_error'
  what():  Negative axis size cannot be inferred. Shape mismatch.
...
/opt/pulsar2/backend/ax650npu/ax650npu_cmodel.so
Aborted (Signal sent by tkill() 10 0)
```

未生成 `precision_analysis_table.txt`。

## 判断

该失败发生在 PA 的 native backend debug/xrun 阶段，不是量化配置解析或 ONNX 导出失败。实际 generator AXMODEL 可在板端通过 `AxEngineExecutionProvider` 正常运行。

使用导出阶段 golden `x/har/style` 在 AX650C 板端单独运行 generator U16：

- waveform cosine `0.99928718`
- MAE `0.00091471`
- max abs diff `0.01769345`

因此 generator-only 后端精度与 `EndToEnd Reference` 指标一致；全链路 waveform 低主要来自前级 `f0/x/har` 输入扰动，而不是 generator 子图自身后端执行崩坏。

# 022 Kokoro SDK HAR 计算与源仓库不一致

## 背景

Kokoro split SDK 中的 CPU `build_harmonic_features` 用于在 `f0ntrain` 与 `generator` 之间构造 `har`。后续真实板端精度分析发现 `f0 -> har -> waveform` 链路非常敏感，用户要求对照源仓库实现确认 `har` 是否计算错误。

## 现象

对比源仓库 `origin/kokoro/istftnet.py`：

- 原始 `SineGen._f02sine` 会对非基频谐波加入随机初始相位。
- 原始 `SineGen.forward` 会加入 voiced/unvoiced noise。
- 原始 `CustomSTFT.transform` 输出 `atan2(imag, real)` phase。
- 原始 `CustomSTFT` 默认 center padding 是 `replicate`。

当前 SDK `build_harmonic_features`：

- 不加入随机初始相位。
- 不加入 source noise。
- STFT phase 固定为 0。
- 使用 zero padding。

这些行为并非凭空产生，而是匹配 `export/export-decoder-split-onnx.py` 中的 `DeterministicSourceModule` 和 `ExportableCustomSTFT`。

## 影响

当前 split pipeline 与 deterministic export golden 基本一致，但和源仓库原始 waveform 已有偏差：

- split deterministic waveform vs source waveform cosine: `0.98193649`
- decoder split waveform vs vocoder split waveform cosine: `0.99999926`

在 generator ONNX 上只将 `har` phase 从 zero 改为 `atan2` 后：

- current zero phase + zero pad waveform vs source cosine: `0.98185417`
- atan2 phase + replicate pad waveform vs source cosine: `0.98782255`

说明当前 `har` 计算相对源仓库确实不完整，尤其是 phase 被置零。

## 结论

如果精度目标是 deterministic split golden，当前 SDK `har` 计算是自洽的；如果精度目标是源仓库原始输出，当前 `har` 计算错误/不完整。

## 后续建议

不能只改 SDK 侧 `har`，因为 generator AXMODEL 当前使用 zero-phase `har` 校准。建议：

1. 恢复至少 `atan2(imag, real)` phase 的 source-like HAR。
2. 用新 `har` 重新生成 generator calibration data。
3. 重编译 generator U16。
4. 分别以 source waveform 和 split deterministic waveform 做板端对分。
