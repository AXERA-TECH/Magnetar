# [006] 杂项：squeezenet 仓库不存在、detr 缺依赖、Pad 算子 opset 警告

## 6.1 local_squeezenet ACQUIRE 失败（401）
```
401 Unauthorized for url 'https://hf-mirror.com/api/models/onnx/squeezenet'
RepositoryNotFoundError
```
**根因**：`models.yaml` 配的 `hf://onnx/squeezenet` 仓库不存在（不是权限问题，是 repo 不存在返回 401）。
**解决**：换正确的 squeezenet 仓库，如 `hf://onnxruntime/...` 或本地放 squeezenet.onnx 走 local 来源。

## 6.2 hf_detr EXPORT 失败（ImportError）
```
DetrForObjectDetection ... ImportError
```
**根因**：DETR 依赖 `timm`、`scipy`（DETR 的 backbone 和匈牙利匹配）。当前环境缺失。
**解决**：`pip install timm scipy`，或用 `optimum-cli export onnx --task object-detection`。
注意 DETR 输出含后处理（box decode），AX 部署通常导出到 logits/pred_boxes 即可。

## 6.3 Pad 算子 opset 转换警告（非致命）
mobilenet / efficientnet 导出时打印：
```
RuntimeError: No Adapter To Version 17 for Pad
adapter_lookup: Assertion `false` failed
```
但随后 `EXPORT OK`，COMPILE 也成功，说明这是 onnx version_converter 尝试升级 Pad 到 opset17
失败的**告警**，torch.onnx.export 的新 dynamo 路径已正常导出。
**结论**：可忽略，不影响产物。若要消除，导出时显式 `opset_version=13`（Pad-13 有 adapter）或用 onnxsim 重写。

## 状态
6.1/6.2 待修（配置 + 依赖），6.3 可忽略。
