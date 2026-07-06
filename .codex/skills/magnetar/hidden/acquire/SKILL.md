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
   - HuggingFace: 设置 `HF_ENDPOINT=https://hf-mirror.co`，用 `huggingface_hub.snapshot_download()` 下载到 `origin/`，私有模型读取 `HF_TOKEN`
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
   - `hf_endpoint`（仅 HuggingFace 来源，必须为 `https://hf-mirror.co`）

## 下载约束

- 所有 HuggingFace 下载必须走 `hf-mirror`；不得直接访问 `https://huggingface.co` 下载模型文件。
- 记录实际使用的 `HF_ENDPOINT`、repo id、revision 和下载命令到 `task.md` 与 `analysis.md`。

## STOP

候选主模型文件超过一个且无法按 README 或命名规则判断时，列出候选项并等待用户选择。
