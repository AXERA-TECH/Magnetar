---
name: acquire
description: 从git仓库、HuggingFace或本地路径获取模型文件到TASK_DIR/origin/
type: hidden
---

# Acquire

## 输入
- `SOURCE`: 模型来源（git URL / hf://org/model[@rev] / 本地路径）
- `source_type`: git | hf | local（由validate-source推断）
- `HF_TOKEN`: 可选，HF私有模型token
- `TASK_DIR`: 工作目录

## 处理逻辑

### git / https
```bash
git clone --depth=1 "$SOURCE" "$TASK_DIR/origin/"
```
克隆后检测模型文件候选：
```bash
find "$TASK_DIR/origin/" \( -name "*.pt" -o -name "*.pth" -o -name "*.onnx" \
  -o -name "*.bin" -o -name "model*.safetensors" \) | head -20
```

### hf://org/model[@revision]
解析格式：`hf://` 前缀后为 `{repo_id}` 或 `{repo_id}@{revision}`。

```python
from huggingface_hub import snapshot_download
import os

token = os.environ.get("HF_TOKEN")
snapshot_download(
    repo_id="{repo_id}",
    revision="{revision_or_None}",
    local_dir="{TASK_DIR}/origin/",
    token=token,
    ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
)
```

如果 `HF_TOKEN` 未设置且下载失败（401/403），进入 `blocked` 状态，提示：
> 需要HuggingFace访问令牌。请设置环境变量 `HF_TOKEN` 或在请求中提供。

### local
```bash
cp -r "$SOURCE" "$TASK_DIR/origin/" 2>/dev/null || \
  ln -s "$(realpath "$SOURCE")" "$TASK_DIR/origin/$(basename "$SOURCE")"
```

## 输出
- `origin_path`: `TASK_DIR/origin/`
- `model_file_candidates`: JSON数组，每项含 `path`、`size_mb`、`type`

## 模型文件优先级
1. 单个 `.onnx` 文件 → 直接进入EXPORT验证
2. `*.pt` / `*.pth` → PyTorch导出流程
3. `config.json` + `*.safetensors` / `*.bin` → HuggingFace transformers格式
4. 多个候选 → **STOP** 让用户选择

## 错误处理
| 错误 | 动作 |
|------|------|
| git clone失败 | retry×1，失败后ask_user |
| HF 401/403 | blocked，提示设置HF_TOKEN |
| 本地路径不存在 | 立即fail，报告路径 |
| 下载超时（>600s） | retry×1 with resume |
