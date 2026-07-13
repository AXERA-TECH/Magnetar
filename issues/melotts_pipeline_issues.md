# MeloTTS COMPILE: AX650 backend AxClip S32 failure

## Context

- Task: `todos/work/20260630-145553-melotts`
- Model: MeloTTS Chinese
- Target: AX650
- Stage: COMPILE
- Initial strategy: export the full `SynthesizerTrn.infer` path as one static ONNX.

## Symptom

The full static ONNX exported and passed ONNXRuntime comparison, but Pulsar2 backend compilation failed on an `AxClip` S32 path for AX650.

## Resolution Used

Do not modify the original MeloTTS source tree. Switch to an AX-friendly split graph:

- encoder: numeric frontend tensors to `z_p`, `pronoun_lens`, `audio_len`
- decoder: `z_p` chunk plus speaker embedding `g` to waveform chunk

The split graph compiled successfully in:

- `todos/work/20260630-145553-melotts/compile/real/encoder/encoder-zh.axmodel`
- `todos/work/20260630-145553-melotts/compile/real/decoder/decoder-zh.axmodel`

## Follow-up

Split compilation only resolves backend legality. It does not by itself guarantee accuracy. SIMULATE still needs to pass before SDK/package generation.
# MeloTTS SIMULATE: split AXMODEL precision failure

## Context

- Task: `todos/work/20260630-145553-melotts`
- Model: MeloTTS Chinese
- Target: AX650
- Stage: SIMULATE
- Static length: `max_len=256`
- Calibration source: upstream Chinese test text
- BERT calibration: zero `bert` and `ja_bert` tensors in this iteration

## Symptom

The real split encoder and decoder compiled with `pulsar2:6.0-lite`, but ONNX vs AXMODEL simulation did not meet the default cosine >= 0.99 gate.

Metrics:

- encoder `z_p`: cosine 0.1441629195, MAE 0.1423239675
- encoder `pronoun_lens`: cosine 0.9451026329, MAE 2.65234375
- encoder `audio_len`: ONNX 479232, AX 131584
- decoder `audio`: cosine 0.0696822629, MAE 0.0176021715

## Analysis

The encoder duration/control outputs are semantically wrong after current quantization, and the decoder waveform path is highly sensitive to quantization. A single calibration sample plus zero BERT features is insufficient for a production-quality compile.

## Recommended Next Steps

1. Regenerate calibration with real BERT and ja_bert features plus multiple Chinese samples.
2. Move duration/control output computation out of the quantized graph or force safer precision for those regions.
3. Add targeted `layer_configs` for sensitive waveform ops/tensors without enabling `highest_mix_precision`.
4. Continue SDK/package only after SIMULATE passes or after the user explicitly accepts an experimental degraded-precision package.
# MeloTTS SIMULATE: duration and flow precision bottleneck

## Context

- Task: `todos/work/20260630-145553-melotts`
- Model: MeloTTS Chinese
- Target: AX650
- Stage: SIMULATE
- Static length: `max_len=256`
- Test text: upstream Chinese test text, first line.

## Result

Core split was used to isolate precision:

- `encoder_core`: `phone/tone/language/bert/ja_bert/g -> m_p/logw`
- CPU postprocess: duration/path expansion
- `flow`: `z_p/y_mask/g -> z`
- `vocoder`: `z/g -> audio`

Metrics:

- `m_p`: cosine 0.9913816168
- `logw`: cosine 0.1080331244
- `flow z`: cosine 0.7981348996
- `vocoder audio`: cosine 0.9963054316

The vocoder subgraph is acceptable by the default cosine gate. Duration/logw and flow are not.

## Probes

- All-FP32 encoder/decoder compile failed on AX650 backend `AxLayerNorm` FP32 tiling.
- DP Conv `weight_data_type=FP32` did not improve `logw`.
- Removing `x_mask` as a static unconnected ONNX output fixed a Pulsar2 quant parser failure in the core split export.

## Recommendation

Do not generate a production SDK/package from the current full split graph. Practical next options:

1. Hybrid runtime: keep duration predictor and flow on CPU, deploy vocoder as AXMODEL.
2. Continue graph surgery on duration predictor and flow, with targeted high precision that avoids FP32 LayerNorm tiling.
3. Improve calibration with real BERT features and more text samples, then re-test.
# MeloTTS RUNONBOARD pyaxengine dependency gap

## 背景

MeloTTS ZH AX650 RUNONBOARD 在 `10.126.35.203` (`pyramid-openclaw`, `AX650C_CHIP`) 上执行。

## 现象

板端默认环境没有 `axengine` Python 包。上传本地 `axengine-0.1.3-py3-none-any.whl` 并用 `pip --target` 临时安装后，Python SDK 能发现：

```text
[INFO] Available providers:  ['AxEngineExecutionProvider']
```

但首次运行失败：

```text
ModuleNotFoundError: No module named 'ml_dtypes'
```

## 处理

当前 MeloTTS 两个 AXMODEL 的 IO 只使用 int32 和 float32，不使用 BF16 IO。RUNONBOARD 在远端临时目录放置最小 `ml_dtypes` stub：

```python
import numpy as _np
bfloat16 = _np.float16
```

随后 Python SDK 使用 `AxEngineExecutionProvider` 跑通，且输出与 `ax_run_model` 完全一致：

- encoder `z` cosine: 1.0
- end-to-end `audio` cosine: 1.0

## 后续建议

生产板端环境应安装完整 pyaxengine 依赖集，至少包括 wheel metadata 中声明的：

- `cffi>=1.0.0`
- `ml-dtypes>=0.1.0`
- `numpy>=1.22`

RUNONBOARD 临时 stub 只能用于当前 int32/float32 IO 模型验证，不应进入交付包或客户环境。
# MeloTTS RUNONBOARD hybrid vocoder calibration mismatch

## 背景

MeloTTS ZH 为复刻源效果改为 hybrid 边界：

- CPU: frontend、BERT、duration/path、flow
- AX650: vocoder slice

CPU hybrid ctx16 切片拼接已验证正确，CPU hybrid audio vs source full infer cosine = `0.9999981672`。

## 现象

把既有 vocoder AXMODEL 放到 hybrid slice 分布上，上板结果明显退化：

- `package_vocoder` board vs source cosine = `0.1222199640`
- `core_v2_vocoder` board vs source cosine = `0.9636271698`

其中 `core_v2_vocoder` 已接近但仍低于用户接受的 `0.98`。

## 原因

hybrid 运行时 vocoder 输入 `z` 来自源 MeloTTS 的 CPU BERT/duration/path/flow 链路。旧 vocoder 编译/校准时的输入分布与该真实 slice 分布不一致，导致 U16 量化误差在板端放大。问题不在切片边界：CPU 侧相同 ctx16 切片拼接几乎等价于 source full infer。

## 修复

使用真实 CPU-BERT/flow hybrid slices 生成校准集，并重新编译 vocoder：

- calibration: `compile/hybrid_ctx16_vocoder/calibration_dataset/`
- config: `compile/hybrid_ctx16_vocoder/pulsar2_config_vocoder_hybrid_ctx16.json`
- AXMODEL: `compile/hybrid_ctx16_vocoder/vocoder/vocoder-hybrid-ctx16-zh.axmodel`
- SHA256: `da494858f08999c313768a2bb8e6d3076ffed26f1452c73dab15c36ebf82e59d`

Pulsar2 配置保持 U16 路线，未开启 `highest_mix_precision`。

## 验证

板子：

- IP: `10.126.35.203`
- hostname: `pyramid-openclaw`
- chip: `AX650C_CHIP`

命令：

```bash
cd /tmp/melotts_hybrid_vocoder_ctx16
rm -rf vocoder_hybrid_ctx16_outputs
mkdir vocoder_hybrid_ctx16_outputs
/opt/bin/ax_run_model -m vocoder-hybrid-ctx16-zh.axmodel \
  -i vocoder_inputs -o vocoder_hybrid_ctx16_outputs \
  -l vocoder_list.txt -w 0 -r 1
```

结果：

- `ax_run_model` 8 个 slice 跑通。
- latency avg = `31.215 ms/slice`。
- board vs CPU hybrid cosine = `0.9987488164`。
- board vs source full infer cosine = `0.9987477014`。

结论：真实 hybrid slice 校准可以恢复 vocoder 上板精度；最终 package 应使用该 hybrid vocoder，而不是旧全 AX 近似包中的 vocoder。
# MeloTTS BERT U16 Duration Boundary Sensitivity

## Context

Model: MeloTTS ZH

Stage: EXPORT / COMPILE / RUNONBOARD

Target: AX650

The source MeloTTS Chinese pipeline depends on `hfl/chinese-roberta-wwm-ext-large` BERT hidden states. For a source-like hybrid package, BERT was converted to AXMODEL so the NPU can run both BERT and vocoder while CPU keeps tokenizer/G2P/word2ph, duration/path, and flow.

## Symptoms

The BERT U16 AXMODEL itself had high feature accuracy:

- token hidden board vs ONNX cosine: `0.9998773927`
- phone-level BERT vs Torch cosine: `0.9999293132`

However, feeding U16 BERT features directly into the MeloTTS duration path caused one duration token to flip:

- Torch `w = 4.9988594`, `ceil = 5`
- AX `w = 5.001221`, `ceil = 6`
- `y_lengths` changed from `743` to `744`
- final audio cosine dropped to about `0.310`

This makes feature-level cosine alone insufficient for validating TTS graphs with discrete duration/path postprocessing.

## Root Cause

MeloTTS converts continuous duration predictions to discrete frame counts through `ceil(w)`. Small BERT quantization errors can move `w` across an integer boundary. Once a single token changes duration, the generated path shifts all following frames, and waveform-level cosine collapses even if all continuous tensors still look accurate.

The BERT ONNX graph also needed cleanup before Pulsar2 compile:

1. `IsNaN` was unsupported.
2. One `And` node caused a float bitwise dump error during quantization; the graph was rewritten to bypass that equivalent mask path.

## Fix

Compile input ONNX:

- `todos/work/20260630-145553-melotts/export/bert/bert-hidden-zh-noand.onnx`

BERT U16 AXMODEL:

- `todos/work/20260630-145553-melotts/compile/bert_u16/bert/bert-hidden-u16-zh.axmodel`

CPU duration stabilization:

```python
floor = torch.floor(w)
near_lower_integer = ((w - floor) < duration_boundary_epsilon) & (floor > 0)
w_for_ceil = torch.where(near_lower_integer, floor, w)
w_ceil = torch.ceil(w_for_ceil)
```

Using `duration_boundary_epsilon = 0.005` fixed the observed U16 flip:

- `w_ceil_changed = 0`
- `z` cosine vs Torch-BERT source: `0.9999983233`
- AX-BERT stable CPU audio vs Torch-BERT source cosine: `0.9994779342`

## Final Board Result

Pipeline:

1. NPU BERT U16
2. CPU token hidden to phone BERT
3. CPU duration/path/flow with `duration_boundary_epsilon=0.005`
4. NPU vocoder ctx16 U16 slices

Board:

- IP: `10.126.35.203`
- chip: `AX650C_CHIP`

Metrics:

- BERT U16 latency: `47.494 ms`
- vocoder latency: `31.196 ms/slice`, 8 slices estimated `249.568 ms`
- board vocoder vs AX-BERT stable CPU full cosine: `0.9989135997`
- board full chain vs Torch-BERT source cosine: `0.9983536661`

The pipeline passes the accepted `cosine >= 0.98` threshold.

## Prevention

- Validate TTS models at waveform level, not just feature-level cosine.
- When duration/path generation is outside the compiled graph, compare `w`, `w_ceil`, and `y_lengths`.
- For quantized BERT or encoder outputs, explicitly test integer-boundary stability before package.
- Do not use S16 automatically just because feature cosine is similar; in this case S16 caused more duration flips than U16.
# MeloTTS encoder_front duration sensitivity

## 背景

MeloTTS ZH 在 AX650 上探索 encoder 转 AXMODEL。目标是尽量把 encoder 前段迁到 NPU，尾部可在 CPU 运行，验收以最终 waveform cosine 为主，用户接受 `cosine >= 0.98`。

## 现象

完整 `enc_p` 上 NPU 后，即使中间特征 cosine 接近，CPU tail 的 duration/path 仍会崩坏：

- `encoder_prior_u16`: `x` cosine `0.98665`，`m_p` cosine `0.98041`，最终 audio cosine `0.0445`。
- `encoder_prior_s16`: 更差。
- `encoder_prior_fullmask_u16`: `x` cosine `0.99245`，`m_p` cosine `0.98797`，最终 audio cosine `0.0285`。

进一步切成 `encoder_front K` 后：

- K=0 audio cosine `0.9989179332`，通过。
- K=1 audio cosine `0.9952257282`，通过。
- K=2 audio cosine `0.9899656606`，通过，是当前最大可用 NPU 切点。
- K=3 audio cosine `0.1190094615`，失败；`y_lengths` 从 `743` 变为 `748`。

## 根因

TTS encoder 后面紧接 duration predictor 和 path generation，`ceil(exp(logw))` 对靠近整数边界的误差非常敏感。中间 feature cosine 不能充分代表最终音频质量。K=3 跨过 speaker conditioning 注入层后，虽然 `front_x` cosine 仍有 `0.9982327365`，但误差已经改变离散 duration，导致后续 path/flow/vocoder 时序偏移。

## 修复/规避

交付边界不要使用完整 `enc_p` AXMODEL，也不要超过 `encoder_front K=2`。

推荐边界：

1. NPU BERT U16。
2. CPU token hidden -> phone-level BERT。
3. NPU `encoder_front K=2` U16。
4. CPU 剩余 encoder/proj/duration/path/flow，保留 `duration_boundary_epsilon=0.005`。
5. NPU vocoder ctx16 U16 slices。

如果更重视复刻质量，使用 K=0 或 K=1；如果更重视 NPU 覆盖且接受 `cosine >= 0.98`，K=2 是实测上限。

## 追加：speaker conditioning 隔离实验

新增 `K=2+cond_add` 结构实验：

- NPU：前两层 transformer + `spk_emb_linear(g)+add`
- CPU：从第 2 层 transformer 继续，跳过重复 speaker add
- AXMODEL：`compile/encoder_front_k2_condadd_u16/encoder_front/encoder-front-k2-condadd-u16-zh.axmodel`
- SHA256：`a432f7ff7d0c0546a084625a691bc6778e8e359e1f3a740a8dde3b9f3881d05e`
- latency：`1.229 ms`
- `front_x` cosine：`0.9997707727`
- `y_lengths`：`743`
- audio vs Torch-BERT source cosine：`0.9898525600`

结论修正：speaker conditioning 的 linear/add 本身不是崩溃点；崩溃发生在 conditioned activation 继续进入第 2 层 transformer 后。当前最大推荐边界是 `K=2+cond_add`，不是完整 K=3。

## 追加：K=3 smooth quant 配置无效

按用户建议对 K=3 增加：

- `transformer_opt_level=1`
- `enable_smooth_quant=true`
- `conv_bias_data_type="FP32"`
- `disable_auto_refine_scale=true`

编译通过，日志确认启用 smooth quant 并检测到多个 outlier：

- `/bert_proj/Conv`
- `/ja_bert_proj/Conv`
- 多个 `LayerNormalization`
- speaker `FullyConnected`
- `/ffn_layers.2/conv_2/Conv`

但上板结果仍失败：

- AXMODEL：`compile/encoder_front_k3_smooth_u16/encoder_front/encoder-front-k3-smooth-u16-zh.axmodel`
- SHA256：`97586f695fc2fffb6a56b596e3339272dbbeb98042461e7b8f939227ddb22bcd`
- latency：`1.666 ms`
- `front_x` cosine：`0.9982297749`
- `y_lengths`：`748`
- audio vs Torch-BERT source cosine：`0.1190234905`

结论：smooth quant 没有解决 K=3 的 duration 翻转。继续推荐 `K=2+cond_add`。

## 追加：layer2 细粒度切分定位到 attention 输出

新增切点：

- `attn_pair`: NPU 输出 layer2 attention 的输入 `x` 和输出 `y`，CPU 执行 `x+y/norm/ffn`。
- `attn_residual`: NPU 执行 `x+y`，CPU 从 `norm1` 继续。
- `norm1`: NPU 执行到 `norm1`，CPU 从 `ffn` 继续。
- `ffn_residual`: NPU 执行到 `ffn` residual，CPU 从 `norm2` 继续。

结果：

- `K2+cond_add`: `w_ceil_changed_count=0`，audio cosine `0.9898525600`。
- `attn_pair`: `w_ceil_changed_count=13`，audio cosine `0.1175674649`。
- `attn_residual`: `w_ceil_changed_count=13`，audio cosine `0.1175230565`。
- `norm1`: `w_ceil_changed_count=13`，audio cosine `0.1175452025`。
- `ffn_residual`: `w_ceil_changed_count=11`，audio cosine `0.1189833739`。
- `attn_pair + Softmax/Where FP32`: `w_ceil_changed_count=13`，audio cosine `0.1178883232`。
- `attn_pair + attention FP32`: `w_ceil_changed_count=14`，audio cosine `0.3466000353`，latency `7.453 ms`。

结论：第 2 层 attention 输出已经导致 duration 翻转；问题不是 residual add、norm1 或 FFN 单独引起的。正式边界保持 `K2+cond_add`。

## 追加：整体 FP32 encoder 不可编译

尝试对 `encoder_prior` 整图使用 FP32：

- 配置：`compile/encoder_prior_fp32_probe/pulsar2_config_encoder_prior_fp32_probe.json`
- 日志：`compile/encoder_prior_fp32_probe/compile_encoder_prior_fp32_probe.log`

结果：编译失败。

失败点：

- `AxLayerNorm`
- `op_1:onnx.LayerNormalization`
- 输入：`/enc_p/encoder/norm_layers_1.0/Transpose_output_0`
- shape：`(1, 256, 192)`
- dtype/output dtype：`FP32`
- 错误：`TileFailException` / `NPUBackendError`

结论：当前 AX650/Pulsar2 后端无法编译整体 FP32 encoder。不要把“整图 FP32”作为 K3 精度修复路径。

## 追加：相邻权重折叠不能修复 layer2 attention

按用户建议尝试 per-channel 相邻权重折叠，而不是单独插入 `scale/unscale`。实现方式：

- q/k/v 输入折叠：`x / scale` 进入投影，同时 `conv_q/conv_k/conv_v.weight * scale`。
- q/k-only 输入折叠：只折叠 query/key，保留 value 分支原状。
- attention context 到 `conv_o` 折叠：`attention(q,k,v) / scale`，同时 `conv_o.weight * scale`。

ONNX/Torch 对分均保持 FP32 语义等价，`front_x` cosine 约 `1.0`。但 AX650 上板后仍失败：

| 变体 | y_lengths | w_ceil changed | audio cosine vs source |
|---|---:|---:|---:|
| q/k/v alpha=0.25 | 750 | 13 | 0.1179939028 |
| q/k/v alpha=0.5 | 751 | 14 | 0.1182144148 |
| q/k/v alpha=0.75 | 749 | 14 | 0.2282359806 |
| q/k/v alpha=1.0 | 749 | 14 | 0.2294173017 |
| q/k/v alpha=1.25 | 750 | 13 | 0.1166806411 |
| q/k alpha=0.75 | 749 | 14 | 0.2275400174 |
| q/k alpha=1.0 | 749 | 14 | 0.2276809106 |
| context->conv_o alpha=0.5 | 750 | 13 | 0.1182935896 |
| context->conv_o alpha=1.0 | 751 | 14 | 0.1165553740 |

结论：相邻权重折叠能改变误差方向，但不能把 duration predictor 的 `ceil(exp(logw))` 拉回稳定区。最佳 audio cosine 只有 `0.2294`，远低于 `0.98` 接受线；`w_ceil` 翻转仍为 `13/14` 个。后续不要继续在该 layer2 attention 上做 alpha sweep，正式边界保持 `K2+cond_add`，第 2 层 attention 留 CPU。
# MeloTTS layer2 attention teacher-student QAT 不稳定

## 背景

MeloTTS ZH 在 AX650 上的最大稳定 encoder 边界是 `K2+cond_add`。如果继续把第 2 层 transformer attention 放到 NPU，duration predictor 的 `ceil(exp(logw))` 会出现离散翻转，导致 waveform 崩溃。

为验证训练级修复是否值得继续，做了最小 teacher-student QAT POC：

- student：只训练 layer2 attention。
- teacher：Torch layer2 attention 输出。
- CPU tail：冻结后续 norm/ffn/encoder/proj/duration。
- loss：attention MSE + duration 边界加权 logw MSE。
- 配置：activation U16、weight S8、matmul input S16、softmax FP32。

## 实现注意事项

`phone_lengths` 不能作为 QAT 图输入。PT2E/AXQuantizer 会把 activation fake quant 插到 Long tensor 路径上，触发：

```text
RuntimeError: expected scalar type Float but found Long
```

修复方式是在 student wrapper 中预计算固定 `x_mask/attn_mask` buffer，forward 只保留 float `x` 输入。

QDQ ONNX 导出需要 import：

```python
import utils.quantized_decomposed_dequantize_per_channel
```

否则 PyTorch 2.10 导出 `convert_pt2e` 后图时缺少 `quantized_decomposed.dequantize_per_channel` lowering。

## 结果

初始 fake quant：

- `w_ceil_changed_count=7`
- `y_lengths=740`

小网格：

| 变体 | status | w_ceil changed | y_lengths |
|---|---|---:|---:|
| `s1_lr1e-4` | passed | 0 | 743 |
| `s5_lr1e-4` | passed | 2 | 741 |
| `s10_lr1e-4` | stopped | 3 | 742 |
| `s20_lr1e-4` | stopped | 4 | 743 |
| `s50_lr1e-4` | stopped | 4 | 743 |
| `s200_lr1e-5` | stopped | 3 | 742 |
| `obs0/1/5_s20` | stopped | 3 | 742 |
| `obs1/5_s200` | stopped | 5 | 744 |

1 步和 5 步能生成合法 QDQ ONNX，ONNX checker 通过，图中包含 `QuantizeLinear/DequantizeLinear`。但 10 步以上、低学习率和冻结 observer 均不能稳定通过 duration 门槛。

## 结论

当前单样本 teacher-student QAT POC 不适合作为交付路径。它证明训练信号能短暂把边界拉回正确侧，但没有稳定优化区间，继续编译/上板价值低。

正式 MeloTTS 交付边界应继续保持 `K2+cond_add`，第 2 层 attention 留 CPU。

## 追加：QAT 框架可疑性判断

单样本最终 checkpoint 不能稳定收敛，确实需要怀疑 QAT 实现或训练设置。但当前证据不支持“QAT.axera 完全不可用”：

- fake-quant forward/backward 能跑通；
- 1 步训练能把 `w_ceil_changed_count` 从 `7` 拉到 `0`；
- 通过短跑的模型能导出合法 QDQ ONNX；
- 关闭 attention Dropout 后，结果与原实验逐项一致，Dropout 不是主因。

关闭 Dropout 检查：

| 变体 | w_ceil changed | y_lengths |
|---|---:|---:|
| `nodrop_s1` | 0 | 743 |
| `nodrop_s5` | 2 | 741 |
| `nodrop_s20` | 4 | 743 |
| `nodrop_s200` | 5 | 744 |
| `nodrop_s200_lr1e-5` | 3 | 742 |

更可能的问题是当前 POC 用 final checkpoint 判定，而 fake quant STE 优化的连续 loss 和 `ceil(exp(logw))` 离散边界不一致，单样本训练会在边界两侧来回漂移。

若后续继续查 QAT 框架，应先做两个 sanity：

- 保存并导出 best checkpoint，而不是 final checkpoint；
- 用同一 AXQuantizer 在简单 Conv/MatMul toy model 上做单样本 teacher-student overfit。如果 toy model 也失败，再怀疑 QAT.axera/PT2E 兼容层。

如果后续继续 QAT，需要升级为多句真实训练/校准集，并同时验收：

- `y_lengths` 与 teacher 一致；
- waveform cosine 达标；
- 多文本无节奏漂移；
- 再进入 QDQ ONNX -> Pulsar2 编译。

## 追加：结论修正

按用户要求先做 toy sanity，再做 best checkpoint，结论需要修正。

Toy sanity 使用同一个 QAT.axera/AXQuantizer，在 `Conv2d + Conv2d + Linear` toy model 上做单样本 teacher-student 过拟合，并给 student 初始权重加入 `0.02` 噪声：

| 变体 | 初始 MSE | 训练后 MSE | ratio | cosine |
|---|---:|---:|---:|---:|
| `noise02_s500_lr1e-3` | `0.01889975` | `5.6627e-08` | `2.996e-06` | `0.9999974370` |
| `noise02_s1000_lr3e-4` | `0.01889975` | `1.3099e-07` | `6.931e-06` | `0.9999936492` |

这说明 QAT.axera/PT2E 的基础 fake-quant 反传和 QDQ 导出链路可用。

MeloTTS POC 的真实问题是 best/final 评估口径：之前用 train-mode fake quant 选择或判断 checkpoint，和 eval/export 口径不一致。修正为每步按 `move_exported_model_to_eval` 的 inference 口径选 best 后：

- best step = `-1`，即训练前 prepared QAT eval 图已经最佳；
- eval 口径 `w_ceil_changed_count=0`，`y_lengths=743`；
- 导出 QDQ ONNX 后用 ONNXRuntime 跑，再接 CPU tail，仍然 `w_ceil_changed_count=0`，`y_lengths=743`；
- pair cosine `0.9999937546`，logw cosine `0.9999999052`。

修正后的判断：

- 不能说 QAT 框架坏；
- 之前的“QAT 不稳定，止损”是 train-mode 指标误导；
- 当前单样本文本上，layer2 attention QDQ ONNX 已通过 duration gate；
- 下一步应尝试 Pulsar2 QDQ 编译和 AX650 上板验证。
