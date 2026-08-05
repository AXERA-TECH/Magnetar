---
name: publish
description: Hidden stage for magnetar. Publish the validated package to GitHub or HuggingFace after asking user for target, repo name, and credentials.
---

# PUBLISH

## STOP 点——必须询问用户

进入本阶段时，暂停并向用户确认以下三项，缺一不可：

1. **发布到哪里？** GitHub / HuggingFace
2. **仓库名叫什么？**（默认 `{model_name}-axmodel`）
3. **凭据在哪？** GitHub 用 `GITHUB_TOKEN` 环境变量，HF 用 `HF_TOKEN`

## 执行

```python
result = magnetar.stages.publish.publish(
    pkg=task_dir / "package",
    target="github",          # 或 "huggingface"
    repo_name="my-model-axmodel",
    token=None,               # None → 自动读 GITHUB_TOKEN / HF_TOKEN 环境变量
    org="AXERA-TECH",         # 可选，GitHub org 或 HF namespace
    model_name="my_model",
)
```

## 分发策略

| 平台 | 内容 | 理念 |
|------|------|------|
| GitHub | 完整包（含 model_convert/ + C++ 源码） | 客户可复现编译流程 |
| HuggingFace | 精简包（models/ + python/ + cpp/ + reports/ + setup.sh + run.sh） | 客户直接用预编译模型和库 |

## HF 特殊处理

- 剔除 `model_convert/`、`.git`、`__pycache__`（cpp/ 编译产物保留）
- README.md 自动添加 YAML frontmatter（license、pipeline_tag、tags）
- 上传到 HF model repo

## GitHub 特殊处理

- 在 package 目录内 `git init` + `git push --force`
- 使用 `https://oauth2:{token}@github.com/{org}/{repo}.git` 认证

## 验证

- GitHub：确认 push 成功，返回 repo URL
- HF：确认 upload_folder 成功，返回 model URL
- 端到端 NPU 跑通（RUNONBOARD 通过）时，发布包 SDK 为 NPU 专用版：
  无 `onnxruntime`/`torch`/`transformers` 运行时回退，依赖仅 `numpy + pyaxengine`
- 检查 `package/NPU_ONLY_SDK.md` 存在且 `python/*_sdk/inference.py` 无 `import onnxruntime`

## 失败处理

- 凭据缺失 → 返回错误信息，重新询问用户
- 推送/上传失败 → 返回错误详情，用户决定重试或跳过
- huggingface_hub 未安装 → 提示 `pip install huggingface_hub`
