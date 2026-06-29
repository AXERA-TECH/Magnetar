---
name: acquire
description: Hidden stage for magnetar. Acquire a remote or local model into TASK_DIR/origin without modifying the source.
---

# ACQUIRE

目标：把 `SOURCE` 获取到 `TASK_DIR/origin/`，并识别候选模型文件和项目入口。

## 步骤

1. 创建 `TASK_DIR/cache/acquire/`，记录来源、时间、命令。
2. 按来源类型处理：
   - Git: `git clone --depth=1 SOURCE TASK_DIR/origin`
   - HuggingFace: 用 `huggingface_hub.snapshot_download()` 下载到 `origin/`，私有模型读取 `HF_TOKEN`
   - HTTP/HTTPS 文件: 下载到 `origin/`
   - 本地目录: 复制目录内容到 `origin/`
   - 本地文件: 复制到 `origin/`
3. 扫描候选文件：
   - 权重：`*.onnx`、`*.pt`、`*.pth`、`*.safetensors`、`*.bin`、`*.pdmodel`
   - 配置：`config.json`、`*.yaml`、`*.yml`
   - 导出脚本：`export.py`、`tools/export*.py`、`scripts/export*.py`
4. 输出 `cache/acquire/manifest.json`：
   - `source`
   - `source_type`
   - `origin_path`
   - `model_file_candidates`
   - `export_script_candidates`
   - `readme_files`

## STOP

候选主模型文件超过一个且无法按 README 或命名规则判断时，列出候选项并等待用户选择。
