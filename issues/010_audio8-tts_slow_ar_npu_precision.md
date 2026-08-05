# Audio8-TTS-Preview-0.6b Slow AR NPU 精度/编译问题

## 现象

1. **INT8/U16 量化精度崩坏**：Slow/Fast AR 的 FP32 激活动态范围过大
   （slow_ar_prefill_a hidden 输出出现 12825 级尖峰），INT8 量化后
   `prefill_b logits` argmax 由 819 漂移到 1481，cosine≈0.36-0.90；
   U16 激活、Percentile 标定、U16+FP32 权重均无法达标（fast_ar cosine 0.90，
   argmax 819→1752）。
2. **全 FP32 编译后 value 张量被破坏**：slow_ar_decode_a 全 FP32 axmodel
   仿真中 `value_delta_*` 输出与 ONNX 完全不符（cosine≈-0.16~0.33），
   `hidden` cosine 0.23；`key_delta_0` 精确匹配而其余输出错误。
   NPU1/NPU2/NPU3、Cos/Sin 量化与否、单/多子图均复现相同数值，指向
   Pulsar2 7.0-lite 后端对大 KV cache（1024 长度）FP32 图的编译缺陷。
3. **板端无法验证**：可用 AX650 板（10.126.35.143）根分区 100% 满、
   ax_run_model 报 "Get model type failed"（运行时与 7.0 产物不兼容）。

## 已排除

- 输入/输出解析错误（与 compile 自身 debug io 对分一致）
- ONNX 导出错误（Torch vs ONNX cosine≈1.0 / codes exact 1.0）
- Snake/Conv-group/LayerNorm/ReduceL2 编译阻塞（均已绕过）
- fast_ar 全 FP32 仿真 cosine=0.999999998（说明仿真器与编译路径基本可用）

## 结论 / 待办

- Slow AR 4 个 axmodel 在 7.0-lite 下未通过精度验证，不能作为板上主路径。
- 候选出路：
  a) Slow AR 按 6 层再切分（4 段）重试 FP32 编译，绕过大图缺陷；
  b) 升级/更换 Pulsar2 版本或 AX 运行时；
  c) AR 部分走 ONNX CPU，codec/fast_ar 走 NPU 的混合部署；
  d) 换用其他 TTS 模型。
