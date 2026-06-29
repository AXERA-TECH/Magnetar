# [002] hf_bert_base COMPILE 失败：校准数据 dtype 与输入不匹配（int64 vs float32）

## 现象
BERT (`google-bert/bert-base-uncased`) 编译时 pulsar2 报：
```
AssertionError: Numpy File(.../input_ids/0000.npy) has dtype(float32),
however corresponding type of inputs(input_ids) is <class 'numpy.int64'>
ErrorCode.QuantError: 3
```

## 根因
benchmark 脚本的 CALIBRATION 阶段对所有模型统一用 `np.random.rand(*shape).astype(np.float32)`
生成校准数据。但 NLP 模型（BERT 等）的输入 `input_ids` / `attention_mask` / `token_type_ids`
是 **int64** 索引张量，不是 float32。pulsar2 校验校准数据 dtype 必须与 ONNX 输入声明一致。

## 关键区别（与 CV 模型对比）
| 模型类型 | 输入 dtype | 校准数据生成 |
|---|---|---|
| CV（resnet/mobilenet 等） | float32 像素 | `np.random.rand().astype(float32)` |
| NLP（bert 等） | int64 token id | `np.random.randint(0, vocab_size, shape).astype(int64)` |

且 NLP 模型通常有多个输入（input_ids + attention_mask + token_type_ids），
每个输入都要单独生成对应 dtype 的校准集，并在 `quant.input_configs` 里分别配置。

## 解决方向
CALIBRATION 阶段应读取 `model_meta.json` 的每个输入 dtype：
- dtype==7 (int64) → `np.random.randint(0, 30000, shape).astype(np.int64)`（vocab 上界从 config 读）
- dtype==1 (float32) → `np.random.rand(*shape).astype(np.float32)`
- attention_mask 通常应为全 1（而非随机）

## 复现
`bash todos/benchmark/run_one.sh hf_bert_base`

## 状态
未解决。benchmark 脚本只支持单输入 float32 CV 模型，多输入 NLP 模型需扩展 CALIBRATION/COMPILE。
