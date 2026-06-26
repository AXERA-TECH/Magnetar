# PP-Human 行人跟踪高精度模型部署问题汇总

模型：`mot_ppyoloe_l_36e_pipeline`，目标芯片：AX650 NPU1，Pulsar2：5.1

---

## [003] EXPORT Paddle2ONNX 2.x PIR 属性转换失败

**问题**：`paddle2onnx==2.0.1` + `paddlepaddle==3.3.1` 转换旧格式 `.pdmodel` 失败。

```text
Failed to convert PaddlePaddle model: (Unimplemented) the 0th elementwise MUST be ir::FloatAttribute
```

**根因**：Paddle 3 走 PIR 路径解析旧 `.pdmodel`，elementwise attribute 不兼容。

**解决**：降级到 Paddle 2.x 环境：

```bash
uv venv cache/export-venv-paddle2 --python python3.10
uv pip install --python cache/export-venv-paddle2/bin/python \
  'paddlepaddle==2.6.2' 'paddle2onnx==1.2.11' numpy onnx onnxruntime
```

转换后固定输入：`image: [1,3,640,640]`，`scale_factor: [1,2]`。

**经验**：PaddleDetection 旧 `.pdmodel` 优先用 Paddle 2.x + Paddle2ONNX 1.x。

---

## [004] COMPILE Pulsar2 5.1 不支持 NonMaxSuppression

**问题**：Pulsar2 5.1 编译含 NMS 的 ONNX 时报错：

```text
KeyError: 'dont support NonMaxSuppression opr in AXOPS/ONNXOPS/CUSTOM_OPS'
```

**根因**：Paddle2ONNX 将 `multiclass_nms3` 转为 ONNX `NonMaxSuppression`，Pulsar2 5.1 不支持该算子。

**解决**：回到 EXPORT，裁剪 `multiclass_nms3` 前的输出（raw boxes/scores），NMS 放在 CPU 后处理。

推荐部署结构：
```text
NPU/AXMODEL:  image -> backbone -> neck -> YOLO head raw outputs
CPU 后处理:   decode -> score threshold -> NMS -> 坐标映射 -> tracker
```

**经验**：检测模型编译前必须确认 ONNX 不含 `NonMaxSuppression`/`BatchedNMS` 等后处理算子。端到端检测包往往默认含 NMS，即使 ORT 可运行，Pulsar2 5.1 也无法编译。

---

## [005] SIMULATE compiled AXMODEL score 精度偏差

**问题**：AXMODEL score 输出与 ONNX cosine 降至 0.983（量化 Reference 为 0.997），NMS 后候选框数量偏少。

```text
boxes cosine: 0.998983
scores cosine: 0.982957
```

**根因**：偏差来自 compiled/NPUBackend 路径，不是普通量化误差。仅将末端 `Sigmoid/Concat` 设为 FP32 不足以修复，误差来自上游分类 head 卷积层。

**当前状态**：以 `compiler.check=0` 版本为较优产物继续。

**经验**：
- 检测模型验证必须同时看 raw tensor cosine 和 NMS 后候选框数量/top-k。
- 混合精度调试应从任务后处理指标出发，逐步向上游扩大 FP32 覆盖范围。

---

## [006] RUNONBOARD 板端输出与 SIMULATE 不一致（未解决）

**问题**：板端输出与 `pulsar2 run` SIMULATE 差异显著，score cosine 约 0.52-0.56。

```text
board axengine vs SIMULATE scores cosine: 0.5612
board ax_run_model vs SIMULATE scores cosine: 0.5246
同一输入多次板端运行间 cosine: ~0.988-0.996（非完全确定性）
```

**状态**：输入 shape/dtype 正确，axengine 和 ax_run_model 均可运行，但两者都与 SIMULATE 不一致。`--vnpu`/`--affinity` 参数无法恢复 SIMULATE 输出。

**可能根因**：板端 runtime/engine 与 Pulsar2 5.1 SIMULATE 后端执行差异；AXMODEL 内部 IO offset 处理方式不一致。

**建议后续**：
- 确认板端 engine 版本（当前 2.12.0s）与 Pulsar2 5.1 的版本匹配关系。
- 用更小模型验证 `pulsar2 run` 与板端 runtime 是否一致。
- 向工具链提交 `axmodel + input.bin + simulate output + board output` 复现包。

**经验**：SIMULATE 通过 ≠ 板端通过。RUNONBOARD 必须拉回 raw tensor 与 SIMULATE 做 tensor 级对比，用 Python runtime 和官方 `ax_run_model` 交叉验证。
