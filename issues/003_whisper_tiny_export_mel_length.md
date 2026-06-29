# [003] hf_whisper_tiny EXPORT 失败：mel 输入长度必须为 3000

## 现象
Whisper (`openai/whisper-tiny`) torch.onnx.export 报：
```
ValueError: Whisper expects the mel input features to be of length 3000,
but found 16. Make sure to pad the input mel features to 3000.
TorchExportError: Failed to export the model with torch.export
```

## 根因
benchmark 脚本对非 vision 模型统一构造 dummy = `torch.zeros(1, 16, dtype=torch.long)`（NLP 默认）。
Whisper 是语音模型，encoder 输入是 mel 频谱特征 `input_features`，
固定 shape 为 `(1, 80, 3000)`（80 mel bins × 3000 帧），且不接受其他长度。
此外 Whisper 是 encoder-decoder 架构，单纯 AutoModel + 单输入无法正确导出。

## 解决方向
1. dummy 应为 `torch.zeros(1, 80, 3000)`，输入名 `input_features`。
2. encoder-decoder 模型应分别导出 encoder 和 decoder（带 KV cache），
   或用 `optimum-cli export onnx --task automatic-speech-recognition`（会拆分多个 onnx）。
3. 多 onnx 子图需分别编译、分别生成 SDK，PACKAGE 时合并。

## 模型类型判别需细化
当前脚本只分 vision / NLP 两类，需增加 speech（whisper/wav2vec 等）类，
按 `model_type` 映射正确的 dummy shape 和输入名。

## 复现
`bash todos/benchmark/run_one.sh hf_whisper_tiny`

## 状态
未解决。encoder-decoder + 语音特征输入超出 benchmark 单图通用脚本能力。
