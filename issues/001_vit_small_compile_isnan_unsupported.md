# [001] hf_vit_small COMPILE 失败：IsNaN 算子不支持

## 现象
ViT (`WinKawaks/vit-small-patch16-224`) 用 transformers + torch.onnx.export 导出后，pulsar2 build 报：
```
KeyError: 'dont support IsNaN opr in AXOPS/ONNXOPS/CUSTOM_OPS'
ErrorCode.OnnxOptimizationError: 13
```

## 根因
HuggingFace ViT 的 attention 实现里包含数值稳定性检查（masked_fill / where + isnan），
导出的 ONNX 图中残留 `IsNaN` 节点。AX NPU 后端不支持该算子。

## 解决方向
1. **首选**：导出时关闭 attention 的 NaN 检查 / 用 `attn_implementation="eager"` 并简化 mask 逻辑。
2. 导出后用 onnx-graphsurgeon 移除 `IsNaN` + 关联的 `Where` 分支（这些通常是恒为 False 的死分支）。
3. 用 onnxsim 常量折叠：若 mask 为静态常量，IsNaN 分支可被折叠消除。
4. 改用 `optimum-cli export onnx --task image-classification`，其导出路径通常更干净。

## 复现
`bash todos/benchmark/run_one.sh hf_vit_small`

## 状态
未解决（benchmark 脚本走的是 torch.onnx.export 通用路径，未做 ViT 专门处理）。
