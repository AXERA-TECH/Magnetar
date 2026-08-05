# XTTS-v2 AX650 部署：风格前端子图 NPU 编译阻塞

## 任务概况

- 模型: `coqui/XTTS-v2`（GPT 30L/1024D + HiFi-GAN 解码器 + ResNet 说话人编码器 + Perceiver 风格编码器）
- 目标: AX650 / NPU3，Pulsar2 镜像 `pulsar2:7.0-lite`，中文优先
- 任务目录: `todos/work/20260804_153344-xtts-v2`
- 结论: **放弃**。5 个 NPU 子图方案中，2 个风格前端子图（cond_encoder / perceiver）因中间值域过大无法通过 Pulsar2 编译；不满足全 NPU 部署目标。

## 已完成工作（可复用）

- ACQUIRE ✅：`model.pth`（1,867,929,118 字节）SHA256=`c7ea20001c6a0a841c77e252d8409f6a74fb423e79b3206a0771ba5989776187` 与 HF 官方 LFS oid 一致。
- EXPORT ✅：6 个子图静态 ONNX（opset 17），Torch-ONNX 对分全部 cos=1.0：
  - `speaker_encoder`（logmel[1,64,601] → dvector[1,512]）
  - `cond_encoder`（mel[1,80,344] → context[1,344,1024]）
  - `perceiver`（context[1,344,1024] → cond[1,32,1024]）
  - `gpt_step0`（emb[1,437,1024] + KV[30,1,16,1039,64] + mask）
  - `gpt_step`（emb[1,1,1024] + KV + pos_idx）
  - `decoder`（latents[1,602,1024] + g[1,512,1] → wav[1,1,670720]）
  - 关键验证：GPT 静态 KV 复刻（自实现 GPT2 eager attention + onehot 写入）与 transformers 参考逐点 cos=1.0；文本 padding 到 402 路径 cos=1.0。
- COMPILE ✅（部分）：`speaker_encoder.axmodel`（8.6MB，NPU 仿真 cos=1.0）编译成功；gpt_step0/gpt_step/decoder 未完成。
- SDK 骨架：Python（numpy 前端，无 torch 依赖）+ C++（AX Engine 封装），分词器/重采样/前端均与参考对齐。

## 阻塞问题 1：OnnxSlim 强制启用 + 3D MatMul+bias 错误融合成 Gemm

**现象**：Pulsar2 检测到模型含 `Constant`/`ConstantOfShape` 算子时强制启用内置 OnnxSlim（`force onnxsim due to found op_type in {'Constant', 'ConstantOfShape'}`，config 的 `enable_onnxsim` 无法关闭）。OnnxSlim 把 3D MatMul（输入 `[1,32,1024]`）与其后 1D bias Add 错误融合为 Gemm，Gemm 的 C 矩阵为 3D/Expand 输出，ORT 执行报 `Invalid bias shape for broadcast`。

**尝试与结论**：
- 把 1D bias initializer 改为 3D `[1,1,D]`：仅部分生效，Expand 型 bias 仍被折叠后融合。
- 反转 Add 输入顺序：OnnxSlim 融合不依赖顺序，无效。
- batch=1 3D MatMul 加 Squeeze/Unsqueeze/Reshape 转 2D：OnnxSlim 优化后仍产生 parser 无法接受的中间结构（to_q/to_kv 报 parser 失败）。
- **最终方案**：导出时把 3D 输入的 `nn.Linear` 等价替换为 Conv1d（kernel=1，`LinearAsConv`），ONNX 中生成 Conv 算子，规避 Gemm 融合。✅ 有效。

## 阻塞问题 2：Einsum 算子不被 Pulsar2 支持

**现象**：关闭 onnx 优化后，量化阶段报 `Op Execution Error: ...Einsum`。

**原因**：cond_encoder/perceiver 的 attention 用 `torch.einsum`，导出为 ONNX Einsum 算子，Pulsar2 NPU 后端不支持。

**方案**：导出时 patch `torch.einsum` 把 4 种 equation（`bct,bcs->bts`、`bts,bcs->bct`、`bhid,bhjd->bhij`、`bhij,bhjd->bhid`）等价转为 MatMul/Transpose；注意 perceiver 用 `from torch import einsum`（模块级绑定），需单独 patch 模块引用。✅ 有效，ONNX 中 Einsum=0。

## 阻塞问题 3：gpt_step0/gpt_step 编译 narrowing_error

**现象**：`EP Error narrowing_error when using None`，发生在 OnnxSlim 优化后（Where 240→0、Unsqueeze 301→61），ORT 加载优化图失败。

**原因**：模型含 1833 个 Constant + 240 个 ConstantOfShape → OnnxSlim 强制启用，折叠/优化后生成 ORT 无法处理的图。

**方案**：导出后 `fix_constant_to_initializer` 把所有 Constant 节点转 initializer、ConstantOfShape 折叠为 zeros initializer，消除强制 onnxsim 的触发条件（gpt_step0/gpt_step 的 Constant=0，ORT 加载正常，cos=1.0）。✅ 已修复，但未重新编译验证。

## 阻塞问题 4（放弃核心原因）：cond_encoder/perceiver 中间值域爆炸

**现象**：
- perceiver 内部中间值域 ±1e11~±1e15（attention logits 达 ±9e15），经 RMSNorm 后输出正常（cond mean/std ≈ -0.02/1.15）。
- cond_encoder 的 attention logits ±1e4~±3.5e4。

**验证**：权重统计正常（std 0.02-0.04，无加载错误）；不同音频输入下 perceiver 内部最大值均为 1e11~1e15 量级（GEGLU 平方放大为模型权重固有特性，非个别数据）；官方模型路径同样存在该数值特性（PyTorch softmax 减 max 可运行，输出语音正常）。

**编译尝试（全部失败）**：
| 方案 | 结果 |
|------|------|
| perceiver INT8（MinMax/KL） | 精度崩，perceiver 层 cosine≈0 |
| perceiver 整图 FP32 | AxSoftmax 在 NPU 后端执行错误 |
| cond_encoder INT8 | 最低层 cosine≈0.002~0.01（attention logits 量化分辨率不足） |
| cond_encoder Percentile | 仍失败 |
| cond_encoder MatMul/Softmax/Conv/Mul → U16 | 仍失败 |
| cond_encoder/perceiver 拆分为独立子图 | 同上，各自失败 |

**结论**：
- perceiver：INT8/U16 均无法表示 ±1e11~1e15 动态范围；FP32 的 softmax Pulsar2 7.0-lite NPU 后端不支持。**确认无法上 NPU**。
- cond_encoder：量级问题而非原理问题，理论上多样化校准数据 + 调参可能改善，但单任务内多轮尝试未果，不再投入。
- 可用替代：这两个子图走 host CPU（onnxruntime，每句一次，几十 ms 量级），NPU 只跑 speaker/gpt/decoder——若后续接受"部分 CPU"方案可复用全部导出产物。

## 阻塞问题 5：hf-mirror 分片下载事故（经验教训）

- `curl -C -` 与 `-r` 混用时 end 边界失效（-C 覆盖整个 range），导致分片超量下载。
- 断点续传用 `-o` 覆盖重写会破坏已下内容偏移；必须用「精确 start-end + `-o`（全量覆盖）」或「`-o - >> file`（shell 追加）」。
- `origin/hash.md5` 内容与实际文件不符，校验以 HF API 的 LFS sha256 为准。

## 遗留可复用资产

任务目录删除前，以下产物可供后续复用（如采用部分 CPU 方案）：
- `export/*.onnx`（6 子图）+ `export/assets.npz` + `export/model_meta.json` + `export/ref_pairs/`
- `export/export_xtts.py`：完整导出链路（含 einsum patch、LinearAsConv、常量转 initializer 等全部 workaround）
- `compile/run_compile.py`：6→4 子图编译配置（speaker/gpt_step0/gpt_step/decoder）
- `sdk/python/xtts_ax650/`：numpy 前端 + 分词器 + GPT 编排（已验证与参考逐点一致）

## 后续建议

1. 若接受混合部署：perceiver/cond_encoder 用 ONNX Runtime CPU（AX650 可装 arm64 wheel），其余 4 子图 NPU，即可交付。
2. 若坚持全 NPU：perceiver 需要模型级数值稳定化重训或权重缩放（改动模型行为，不可直接量化）；cond_encoder 可试多样化校准数据 + 调 Percentile 百分位。
3. 可尝试完整版 `pulsar2:7.0`（非 lite）验证 FP32 softmax 支持，但成功概率低。
