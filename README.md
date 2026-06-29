# Magnetar

将任意来源模型转换为 AX 芯片 axmodel，并自动生成 Python/C++ 推理 SDK。

## 流程

```
SOURCE (git / HuggingFace / 本地)
  └→ ACQUIRE → INIT → EXPORT → COMPILE → SIMULATE → SDK-GEN → [RUNONBOARD] → PACKAGE
```

## 快速开始

```text
/axmodel-pipeline hf://ultralytics/assets AX650
/axmodel-pipeline https://github.com/xxx/resnet AX620E
/axmodel-pipeline /data/models/yolo.pt AX650
```

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `SOURCE` | 是 | `hf://org/model[@rev]`、git URL、本地路径 |
| `TARGET_HARDWARE` | 是 | `AX650` \| `AX620E` |
| `MODEL_NAME` | 否 | 默认从 SOURCE 推断 |
| `SDK_LANG` | 否 | `python` \| `cpp` \| `both`（默认 both） |
| `TOOLCHAIN_FILE` | 否 | aarch64 交叉编译 toolchain.cmake 路径 |
| `HF_TOKEN` | 条件 | 私有 HuggingFace 模型必须提供 |
| `BOARD` | 条件 | RUNONBOARD 阶段需要，格式 `user@host` |

## 产物

```
TASK_DIR/
  export/
    model.onnx
    model_meta.json        # I/O tensor 元数据
    tokenizer/             # transformers 模型含此目录
  compile/
    model.axmodel
  simulate/
    accuracy_report.md
  sdk/
    python/{model_name}_sdk/   # Python 推理 SDK
    cpp/                        # C++ SDK + toolchain-aarch64.cmake
  package/                      # 最终打包产物
```

## Skills

- `.codex/skills/axmodel-pipeline/` — 入口 skill（新设计）
- `.codex/skills/magnetar-deploy/` — 阶段执行 helper（EXPORT/COMPILE/SIMULATE/RUNONBOARD）

## 工作流规范

`.codex/workflows/axmodel-pipeline.yaml`
