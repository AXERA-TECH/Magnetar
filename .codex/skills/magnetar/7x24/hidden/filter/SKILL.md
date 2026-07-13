---
name: filter
description: Hidden stage for 7x24. Filter models by task type and size, exclude incompatible architectures.
---

# FILTER

对发现的模型做二级过滤和风险评估。

## 过滤规则

### 自动拒绝

- `pipeline_tag` 为 `text-generation` 或 `conversational`（纯 LLM）
- 缺少模型权重文件（HF 仅有 config 无 safetensors/pt）
- ONNX 模型且 opset < 11

### 风险标记（继续但标记）

- `pipeline_tag` 为 `text-to-speech`、`automatic-speech-recognition`（语音模型结果不确定）
- 模型架构含 Transformer 但非纯 LLM（可尝试，标记 `transformer_risk: true`）
- 模型大小 > 1GB（编译时间长）
- 输入非固定 shape（需 EXPORT 阶段静态化）

### 转正过滤

符合以下条件之一的直接通过：

- `pipeline_tag` 为 `object-detection`、`image-classification`、`image-segmentation`
- 模型名称含 `yolo`、`mobilenet`、`resnet`、`efficientnet`、`vit`、`segformer`
- 源仓库有 ONNX 导出脚本

## 输出

更新 `queue.json`，为每个模型添加标签：

```json
{
  "pending": [
    {
      "source": "hf:user/model",
      "task": "object-detection",
      "confidence": "high",
      "tags": ["yolo", "detection"],
      "estimated_size_mb": 150
    }
  ]
}
```

`confidence` 取值：`high`（视觉模型）| `medium`（语音/混合架构）| `low`（未知但非 LLM）。

## 验证

- 滤掉的模型记录到日志，含拒绝原因。
- `pending` 队列中每个模型都有 `confidence` 和 `tags`。
