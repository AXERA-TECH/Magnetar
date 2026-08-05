# [012] NeuTTS-2E AX650：llm_build head_dim 断言 + host-KV 架构 RTF 上限

## 背景

`neuphonic/neutts-2e`（Qwen3-2E 语音 LLM，28 层，hidden=512，12 头 × head_dim=128，
4 KV 头，vocab 217232）转 AX650 / NPU3。全程踩坑记录，供后续 LLM 类 TTS 参考。

## 结论（一句话）

该模型 **无法走 Pulsar2 `llm_build`（on-NPU KV）**，只能用自研静态 ONNX + host 管理 KV；
该架构下 RTF 有硬地板（实测融合后完整管线 RTF≈5.6），**实时（RTF≤1）不可达**，
除非 Pulsar2 支持大 head_dim 布局或换模型。

## 关键证据

### 1. llm_build 断言（所有版本一致）

`pulsar2 llm_build/llm_build2`（7.0-lite、7.0 完整、6.0-lite、20260716/20/22 开发版全部验证）
在 `llama_test.build_layer` 断言：

```
num_attention_heads * head_dim == hidden_size
```

本模型 12×128=1536 ≠ 512 → AssertionError（裸断言无信息，靠 monkeypatch 打印入参定位：
`build_layer(lastN, layer_num, m_type, w_dtype, al, cfg)`，frame locals `_var_var_45=12`/`_var_var_26=512`）。
对照实验：config 改 heads=4（4×128=512）断言消失、进入权重形状错误 → 确认该约束。
注意：官方 6.0 文档示例 Qwen3-0.6B（hidden 1024、16 头、head_dim 128，16×128≠1024）能编译，
说明工具链本应支持，7.0 可能回归。

### 2. host-KV 架构的 RTF 拆解（AX650N 实测）

| 项 | 数值 |
|---|---|
| 逐层 decode_l0 单次调用 | 4.16 ms（KV 8.4MB 搬移 1.73ms + 其余 2.4ms） |
| prefill_l0 单次调用 | 4.91 ms（计算量 5 倍，耗时相近 → 固定调用开销 ~2.4-4ms） |
| 每 token 28 层调用 | ~116 ms + post + 采样 → RTF 8.95 |
| 融合 28 层单模型 | decode 单步 56 ms（KV 117MB/1024ctx ~24ms + NPU 执行 ~32ms） |
| 融合后完整管线 | RTF 5.64（8.89 tokens/s，AX650N） |

结论：瓶颈 = host 管理 KV 的全量搬移 + 每层固定调用开销，**不是 NPU 算力**。
1024 上下文 fp32 KV = 117MB/token，搬移地板 ~24ms，已超 50Hz 实时预算（20ms）。

## 踩坑清单

### A. 导出/编译
1. **transformers 5.x 的 Qwen3 无条件使用 q_norm/k_norm（QK-norm，RoPE 前）**。
   Pulsar2 默认 `use_qk_norm=False` → 必须 `--model_config` 显式
   `"use_qk_norm": true, "qk_norm_after_rope": false`，否则权重解析错乱。
2. **`layer_types` 字段**（config 里 28×full_attention）不是断言原因，可留可删。
3. **ONNX 静态化细节**：
   - 权重 MatMul 需要 `.T`（[out,in]→[in,out]）
   - opset 17：Unsqueeze/Split 的 axes/split 必须是输入张量，不能用属性
   - SSA 冲突：initializer 名与节点输出名不能相同
   - `output_hidden_states` 最后一层输出会被 final norm 覆盖（h[28]≠layer27 输出），
     验证时需 hook 捕获真实 layer 输出
4. **decode 层必须输出当前 token 的 K/V**（host 需要回写 cache）；
   用 cache 宽 2047 + 当前 K/V 尾部拼接（concat）保持静态 shape，
   mask 放行 0..pos-1 与最后一列。
5. **FP16 输入 dtype 不被量化器支持**（`KeyError DataType.FP16`，Cast 硬件规格缺失）→ 用 FP32。
6. **layer_configs 的 `data_type/weight_data_type` 对 MatMul 精度几乎无效**：
   S8/FP16/S16 权重输出逐位一致（build 表仍显示 FP32，实际权重按 S8）。
   build 的 check（cos=1.0）对比的是**量化后参考**，不是 fp32 ONNX —— 硬件真实误差更大
   （INT8 全量化 prefill_l0 vs ONNX cos=0.19；FP32 激活版本 0.96）。
7. **解码器 ONNX（NeuCodec）**：动态 shape + 48 个 Sequence 算子
   （SplitToSequence/SequenceAt）→ 先固定输入 shape，替换为 Slice+Squeeze，
   再 onnxsim 折叠（Sequence 算子残留时 onnxsim 会卡死）；大图（782MB）编译 OOM/过慢，
   交付用官方 int8 ONNX + onnxruntime CPU。
8. **并行 pulsar2 build 会产出坏 axmodel**：出现过 decode_l4 丢输出（仅剩 out）、
   prefill_l1 毒化运行时（单独加载 OK，加载后再加载任何模型都报
   `Failed to load model`，但仿真器正常）→ **顺序编译 + 板端逐模型加载验证 + md5 比对**。
   坏版本特征：同配置重复编译 md5 不同。

### B. 板端（axengine 0.1.3）
9. **共享板反复加载/卸载会耗尽 CMA**（`CmaFree` 归零），后续加载报
   `Failed to load model`，只能重启恢复 → 减少加载循环，一次跑完。
10. **`ulimit -n=1024`** 会挡住 57 个会话（每会话多个 FD）→ 跑前 `ulimit -n 65535`。
11. `pulsar2 run` 多输入格式：`input_dir/sample0/<tensor名>.bin` + list 文件每行一个样本名
    （不是每行一个输入文件）。
12. 板端磁盘：bundle tar 与解压目录要留双倍空间，传完立刻删 tar。

### C. SDK/管线
13. `emotion="neutral"` 无 `<|NEUTRAL|>` token → 当作 None 处理。
14. 采样 top-k(50) 随机：量化导致的微小 logit 差异会让 token 序列完全发散
    （token 匹配率 0%），音频相似度低属预期；精度验证应看确定性部分
    （首 token logits cosine / 逐层 hidden cosine）。

## 建议

1. 找 AXERA / 新 Pulsar2 支持大 head_dim 布局（Qwen3-0.6B 同款），llm_build 后
   RTF 可到 ~0.3-0.5。
2. 若维持 host-KV：融合 28 层 + 收窄上下文（1024）是当前最优（RTF 5.6），
   进一步只能减 reference 长度/降 KV 精度。
3. 新任务先查本文档与 007/010/011（同为 TTS/LLM 上 AX650 的坑）。

## 产物去向

任务目录（todos/work/20260804_154030-neutts2e）已按用户要求删除；
交付包与中间产物不再保留。本文档为唯一沉淀。
