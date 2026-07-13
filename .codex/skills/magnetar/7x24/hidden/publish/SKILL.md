---
name: publish
description: Hidden stage for 7x24. Publish converted models to HuggingFace (binary) and GitHub (source).
---

# PUBLISH

将 PACKAGE 产物分发到 HF 和 GitHub。

## 前置条件

- RUNONBOARD 阶段通过（板端推理正确）
- SIMULATE cosine >= 0.99
- `package/` 目录完整

## HF 发布

HF repo: `AXERA-TECH/<model-name>`

内容（二进制为主，开箱即用）：

```
models/model.axmodel
models/model_meta.json
cpp/bin/visdrone_detect
cpp/lib/libdet.so
cpp/include/
python/
demo/
README.md (YAML frontmatter)
```

步骤：

```bash
export HF_ENDPOINT=https://hf-mirror.com

# 创建 repo
python3 -c "
from huggingface_hub import HfApi
api = HfApi()
api.create_repo('AXERA-TECH/<model-name>', repo_type='model', exist_ok=True)
"

# 上传文件
python3 -c "
from huggingface_hub import HfApi
api = HfApi()
import os
for root, dirs, files in os.walk('package_hf'):
    for f in files:
        path = os.path.join(root, f)
        rel = os.path.relpath(path, 'package_hf')
        api.upload_file(path, rel, 'AXERA-TECH/<model-name>', repo_type='model')
"
```

## GitHub 发布

GitHub repo: `ml-inory/<model-name>.axera`

内容（源码 + 复现）：

```
models/model.axmodel
models/model_meta.json
cpp/CMakeLists.txt
cpp/toolchain-aarch64.cmake
cpp/examples/
python/
model_convert/
reports/
demo/
README.md
```

步骤：

```bash
cd package
git init
git remote add origin git@github.com:ml-inory/<model-name>.axera.git

# 创建 GitHub repo
gh repo create ml-inory/<model-name>.axera --private --push --source .

# 创建 Release
gh release create v1.0.0 models/model.axmodel --title "Initial release"
```

## 失败处理

- HF 推送失败：重试 3 次，指数退避，仍失败则记录到 `failed` 队列。
- GitHub 推送失败：同上。
- 两边都成功后写入 `completed` 队列。

## 命名规则

模型名从 `model_meta.json` 的 `model_name` 字段读取，转为小写下划线格式：

```
YOLO11s-visdrone → yolo11s-visdrone
MobileNetV2-ImageNet → mobilenetv2-imagenet
```

HF repo 仅用模型名，GitHub repo 加 `.axera` 后缀。

## 验证

- HF repo 存在且包含 `model.axmodel` 和 `README.md`。
- GitHub repo 存在且包含 `model_convert/` 目录。
- `queue.json` 中模型已从 `pending` 移到 `completed`。
