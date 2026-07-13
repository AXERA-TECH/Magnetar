---
name: publish
description: Hidden stage for 7x24. Publish converted models to HuggingFace (binary + SDK) and GitHub (source + model_convert).
---

# PUBLISH

将 PACKAGE 产物分发到 HF 和 GitHub。必须包含 python SDK 和 model_convert。

## 发布清单

每个模型必须包含：

### HF（开箱即用）
```
models/model.axmodel
models/model_meta.json
python/inference.py       # 模型专用推理类
python/example.py          # 可直接运行的示例
python/requirements.txt
README.md                  # YAML frontmatter
```

### GitHub（源码 + 复现）
```
models/model.axmodel
models/model_meta.json
python/inference.py
python/example.py
python/requirements.txt
model_convert/export_onnx.py
model_convert/pulsar2_config.json
model_convert/requirements.txt
model_convert/README.md
README.md
```

## 执行步骤

### 1. 准备发布目录

```bash
mkdir -p /tmp/publish/<model>/{models,python,model_convert}
```

从 `TASK_DIR` 复制所有产物。

### 2. HF 发布

```bash
export HF_ENDPOINT=https://hf-mirror.com
python3 << PYEOF
from huggingface_hub import HfApi, create_repo
api = HfApi()
repo = "AXERA-TECH/<model-name>"
create_repo(repo, repo_type="model", exist_ok=True)
for f in file_list:
    api.upload_file(
        path_or_fileobj=f"/tmp/publish/<model>/{f}",
        path_in_repo=f,
        repo_id=repo,
        repo_type="model"
    )
PYEOF
```

> **注意**: `create_repo` 和 `upload_file` 都需要 `repo_type="model"`。
> `upload_file` 的参数名是 `path_or_fileobj` 和 `path_in_repo`，必须用关键字参数。

### 3. GitHub 发布

```bash
cd /tmp/publish/<model>
git init
git add -A
git commit -m "<model> AX650 deployment"

# 创建 repo 并推送
gh repo create ml-inory/<model>.axera --private --push --source .
```

> **注意**: `gh repo create --push` 会自动设置 remote 为 `origin`。
> 如果已存在同名 repo，先 `gh repo delete`。Token 需 `delete_repo` 权限。

### 4. 验证

```bash
# HF
curl -s "https://hf-mirror.com/AXERA-TECH/<model>/raw/main/README.md" | head -5

# GitHub (private repo)
gh api repos/ml-inory/<model>.axera/contents/ --jq '.[].name'
```

## SDK 模板

### 分类模型 (image-classification)

`python/inference.py`:
```python
import numpy as np, axengine

class Classifier:
    def __init__(self, model_path):
        self.sess = axengine.InferenceSession(model_path)
        self.input_name = self.sess.get_inputs()[0].name
    def classify(self, image: np.ndarray):
        return self.sess.run(None, {self.input_name: image})[0]
```

### 检测模型 (object-detection, YOLO)

按 `sdk-gen/SKILL.md` 的 YOLO 模型要求，集成 libdet.axera。

### 分割模型 (image-segmentation)

参考分类模型模板，输出处理适配分割任务。

## model_convert 模板

```python
# export_onnx.py - 从原始权重导出 ONNX
```

```json
// pulsar2_config.json - 实际使用的编译配置
// calibration_std=255 对齐 ONNX [0,1] 输入
```

```text
# requirements.txt
# 导出依赖 (timm/torch/onnx 等)
# Pulsar2 通过 Docker 提供: https://hf-mirror.com/AXERA-TECH/Pulsar2
```

## 故障处理

| 错误 | 处理 |
|------|------|
| HF `upload_file` signature error | 确认用 `path_or_fileobj=` 和 `path_in_repo=` 关键字 |
| GitHub `Name already exists` | `gh repo delete --yes` 后重试，或 `gh repo create` 不带 `--push` |
| GitHub push rejected | `git pull --rebase` 后再 push |
| README 被覆盖 | 检查 `cat > README.md << EOF` 中的 `$VAR` 展开，用 `<< 'EOF'` 避免 |
