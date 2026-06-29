---
name: axmodel-pipeline
description: >
  将任意来源模型（git仓库、HuggingFace仓库、本地路径）转换为AX芯片axmodel，
  并自动生成Python/C++推理SDK。
  触发条件：用户提供模型来源并要求转换或部署到AX芯片。
---

# axmodel-pipeline

始终用中文与用户沟通。严格按照 `ACQUIRE → INIT → EXPORT → COMPILE → SIMULATE → SDK-GEN → (RUNONBOARD) → PACKAGE` 顺序执行。遇到 `STOP` 必须暂停等待用户确认。

工作流规范见 [../../workflows/axmodel-pipeline.yaml](../../workflows/axmodel-pipeline.yaml)。

## 输入参数

从用户请求中解析，缺少必要参数时在最近的STOP点询问：

| 参数 | 必填 | 说明 |
|------|------|------|
| `SOURCE` | 是 | `git://`、`https://github.com/...`、`hf://org/model[@rev]`、本地路径 |
| `TARGET_HARDWARE` | 是 | `AX650` 或 `AX620E` |
| `MODEL_NAME` | 否 | 默认从SOURCE basename推断 |
| `TASK_DIR` | 否 | 默认 `todos/work/TIMESTAMP-MODEL_NAME/` |
| `HF_TOKEN` | 条件 | HuggingFace私有模型必须提供，读取环境变量 `HF_TOKEN` |
| `SDK_LANG` | 否 | `python`、`cpp`、`both`（默认both） |
| `BOARD` | 条件 | RUNONBOARD阶段需要，格式 `user@host` |

## 阶段执行

### ACQUIRE
委托 [hidden/acquire/SKILL.md](hidden/acquire/SKILL.md)。

按SOURCE类型处理：
- **git/https仓库**: `git clone --depth=1 SOURCE TASK_DIR/origin/`，然后自动检测模型文件（`.pt`、`.pth`、`.onnx`、`.bin`、`config.json`）
- **hf://org/model**: 使用 `huggingface_hub.snapshot_download()`，私有模型需 `HF_TOKEN`
- **本地路径**: 验证存在后复制到 `TASK_DIR/origin/`

产出：`origin_path`、`model_file_candidates`（候选模型文件列表）

**STOP（模型文件不明确时）**: 列出候选文件，询问用户选择主模型文件。

### INIT
复用现有magnetar-deploy的INIT逻辑，额外创建 `sdk/python/`、`sdk/cpp/` 目录。

目录结构：
```
TASK_DIR/
  origin/          # 原始模型工程
  export/          # ONNX导出
  compile/         # axmodel编译产物
  simulate/        # 仿真结果
  sdk/
    python/        # Python SDK
    cpp/           # C++ SDK
  package/         # 最终打包
  cache/
  task.md
  analysis.md
```

### EXPORT → COMPILE → SIMULATE
复用 `.codex/skills/magnetar-deploy` 中对应阶段逻辑。

EXPORT额外要求：导出时捕获并保存 `model_meta`（I/O tensor名称、shape、dtype），写入 `export/model_meta.json`，用于SDK生成。

#### HuggingFace Transformers 格式自动导出

检测条件：`origin/` 下存在 `config.json` 且含 `*.safetensors` 或 `pytorch_model*.bin`。

**优先方式：`optimum` CLI**（覆盖大多数 transformers 架构）
```bash
pip install optimum[exporters] -q
optimum-cli export onnx \
  --model "$TASK_DIR/origin/" \
  --task "{auto_detected_task}" \
  "$TASK_DIR/export/"
```
`task` 从 `config.json` 的 `architectures` 字段自动推断（见映射表）：

| architectures字段含 | optimum task |
|---|---|
| ForCausalLM | text-generation |
| ForSequenceClassification | text-classification |
| ForTokenClassification | token-classification |
| ForQuestionAnswering | question-answering |
| ForImageClassification | image-classification |
| ForObjectDetection | object-detection |
| 其他 / 未知 | auto（让optimum自己判断） |

**回退方式：torch.onnx.export**（当optimum失败或模型为自定义架构时）
```python
import torch, sys
sys.path.insert(0, f"{TASK_DIR}/origin/")
# 读取 config.json，尝试加载模型
from transformers import AutoModel, AutoConfig
config = AutoConfig.from_pretrained(f"{TASK_DIR}/origin/")
model = AutoModel.from_pretrained(f"{TASK_DIR}/origin/")
model.eval()
# 构造dummy输入（根据 model_type 选择合适shape）
dummy = torch.zeros(1, 1, dtype=torch.long)  # 默认NLP dummy
torch.onnx.export(model, dummy, f"{TASK_DIR}/export/model.onnx",
                  opset_version=17, dynamic_axes=None)
```
若模型包含 tokenizer，额外复制 `tokenizer*` 文件到 `export/tokenizer/`，并在 `model_meta.json` 中记录 `tokenizer_path`，供 Python SDK 生成时自动包含 tokenizer 封装。

**STOP（transformers导出失败时）**：列出错误和已尝试的方式，询问用户提供自定义导出脚本路径。

### SDK-GEN（新阶段）
SIMULATE通过后执行。委托 [hidden/sdk-gen/SKILL.md](hidden/sdk-gen/SKILL.md)。

精度达标（余弦相似度 > 0.99）时**自动继续**，无需用户确认。仅精度不达标时 **STOP**：展示报告，询问是否调整配置重试。

Python SDK和C++ SDK并行生成。

### RUNONBOARD（可选）
启动前已提供 `BOARD` 参数 → 自动执行 RUNONBOARD；未提供 → 直接进入 PACKAGE，**不询问**。

### PACKAGE
将以下内容打包到 `TASK_DIR/package/`：
- `*.axmodel`
- `sdk/python/`（含 `README.md` 和使用示例）
- `sdk/cpp/`（含 `README.md` 和使用示例）
- `accuracy_report.md`
- `task.md`

## 质量门槛

继承 magnetar-deploy 的所有质量门槛，追加：
- `export/model_meta.json` 必须存在且包含完整I/O信息
- Python SDK：`python -c "from {model_name}_sdk import {ModelName}Inference"` 必须成功
- C++ SDK：`cmake -S sdk/cpp -B sdk/cpp/build` 必须成功（有cmake时执行）
