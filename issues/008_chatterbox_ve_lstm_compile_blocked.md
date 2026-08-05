# [008] Chatterbox VE LSTM Pulsar2 编译失败

## 现象

`export/ve.onnx`（VoiceEncoder：3 层 LSTM(40→256) + Linear + ReLU + L2 norm）用 `pulsar2:7.0-lite` 编译到 AX650/NPU3 失败。

```text
transformation: optimization.AxDynamicQuantizedLSTM_decomposition
KeyError: 'node_LSTM_184_lstm_oc'
...
KeyError: 'node_LSTM_184'
CodeException: (<ErrorCode.FrontendError: 6>, KeyError('node_LSTM_184'))
```

opset 17 与（实际导出的）opset 18 均复现同一错误。

## 处理

VE 保持 CPU 执行（模型 5.7MB，仅参考音频预处理阶段运行一次）。SDK 中 speaker_emb 用 torch CPU 计算，不阻塞交付。

## 后续

若需 NPU 化，需等 Pulsar2 LSTM 分解修复，或手工把 LSTM 展开为 gates/Scan（低优先级）。
