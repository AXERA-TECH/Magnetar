"""PUBLISH: 将交付包发布到 GitHub 或 HuggingFace。

STOP 点：询问用户发布目标、仓库名、凭据。
GitHub → 源码 + model_convert（客户可复现）
HuggingFace → 预编译模型（客户直接用），不含 model_convert/ 和 C++ 源码
"""
import json, os, shutil, subprocess, tempfile
from pathlib import Path
from typing import Literal


def publish(pkg: Path, target: Literal["github", "huggingface"],
            repo_name: str, token: str | None = None,
            org: str | None = None, model_name: str = "model") -> dict:
    """发布交付包到指定平台。

    Args:
        pkg: package 目录路径
        target: "github" 或 "huggingface"
        repo_name: 仓库名（不含 org 前缀）
        token: 访问令牌。GitHub 用 GITHUB_TOKEN 环境变量，HF 用 HF_TOKEN
        org: GitHub org 或 HF namespace（可选）
        model_name: 模型名，用于 README 标题

    Returns:
        {"ok": bool, "url": str, "errors": list}
    """
    if target == "github":
        result = _publish_github(pkg, repo_name, token, org)
    elif target == "huggingface":
        result = _publish_huggingface(pkg, repo_name, token, org, model_name)
    else:
        result = {"ok": False, "url": "", "errors": [f"未知发布目标: {target}"]}

    from magnetar.stages.state import mark_stage
    mark_stage(
        pkg.parent, "PUBLISH",
        status="done" if result.get("ok") else "blocked",
        artifacts={"publish_url": result.get("url", "")},
        summary=f"PUBLISH {'成功' if result.get('ok') else '失败'}: {result.get('url', '')}",
    )
    return result


def _publish_github(pkg: Path, repo_name: str, token: str | None, org: str | None) -> dict:
    """发布到 GitHub：初始化 git 仓库并推送。

    GitHub 分发完整源码 + model_convert，客户可复现编译流程。
    """
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        return {"ok": False, "url": "", "errors": ["缺少 GITHUB_TOKEN，请设置环境变量或在 .magnetarrc 中配置"]}

    org_prefix = f"{org}/" if org else ""
    remote_url = f"https://oauth2:{token}@github.com/{org_prefix}{repo_name}.git"
    public_url = f"https://github.com/{org_prefix}{repo_name}"

    try:
        _init_and_push(pkg, remote_url, "GitHub 发布")
        return {"ok": True, "url": public_url, "errors": []}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "url": public_url, "errors": [f"Git push 失败: {e.stderr}"]}


def _infer_pipeline_tag(task: str) -> str:
    """由任务类型推断 HF pipeline_tag（宽松子串匹配）。"""
    t = (task or "").lower()
    if any(k in t for k in ("noise", "audio", "speech", "tts", "voice", "vocoder", "asr", "vad")):
        return "audio-to-audio"
    if any(k in t for k in ("text", "llm", "chat", "generation", "question-answering")):
        return "text-generation"
    if any(k in t for k in ("detection", "detect", "segment")):
        return "object-detection"
    if any(k in t for k in ("classif", "image", "vision", "ocr")):
        return "image-classification"
    return "other"


def _build_hf_frontmatter(flow: dict | None, meta: dict | None, model_name: str) -> str:
    """生成 HF README 的 YAML frontmatter。

    license 优先取 model_flow.json（ACQUIRE 已按源仓库 LICENSE 推断），
    其次 model_meta.json，再没有就由调用方兜底（mit）。
    """
    flow = flow or {}
    meta = meta or {}
    task = str(flow.get("task") or meta.get("task") or "")
    pipeline_tag = _infer_pipeline_tag(task)
    license_id = str(flow.get("license") or meta.get("license") or "mit")
    return f"""---
license: {license_id}
pipeline_tag: {pipeline_tag}
tags:
- axmodel
- axera
- {model_name}
---
"""


def _publish_huggingface(pkg: Path, repo_name: str, token: str | None,
                          org: str | None, model_name: str) -> dict:
    """发布到 HuggingFace：仅上传预编译模型 + Python SDK。

    HF 分发预编译产物（客户直接用），不含 model_convert/（复现编译脚本）。cpp/ 编译产物（.so、可执行文件）全部保留。
    README 需添加 YAML frontmatter。
    """
    token = token or os.environ.get("HF_TOKEN")
    if not token:
        return {"ok": False, "url": "", "errors": ["缺少 HF_TOKEN，请设置环境变量或在 .magnetarrc 中配置"]}

    org_prefix = f"{org}/" if org else ""
    repo_id = f"{org_prefix}{repo_name}"
    public_url = f"https://hf-mirror.com/{repo_id}"

    # 构建 HF 专用的精简包
    with tempfile.TemporaryDirectory(prefix="magnetar_hf_") as tmp:
        hf_dir = Path(tmp) / repo_name
        shutil.copytree(pkg, hf_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("model_convert", ".git", "__pycache__", "*.pyc"))

        # 上传空白 config.json 用于 HF 下载追踪
        (hf_dir / "config.json").write_text("{}", encoding="utf-8")

        # HF README 加 YAML frontmatter：
        # - task/license 优先读 ACQUIRE 记录的 model_flow.json（origin/）
        # - license 缺省按源仓库 LICENSE 推断（infer_source_license），再无则 mit
        readme = hf_dir / "README.md"
        if readme.exists():
            original = readme.read_text(encoding="utf-8")
            flow: dict = {}
            flow_path = pkg.parent / "origin" / "model_flow.json"
            if flow_path.is_file():
                try:
                    flow = json.loads(flow_path.read_text(encoding="utf-8"))
                except Exception:
                    flow = {}
            meta: dict = {}
            meta_path = hf_dir / "models" / "model_meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            if not flow.get("license") and not meta.get("license"):
                from magnetar.stages.acquire import infer_source_license
                flow["license"] = infer_source_license(pkg.parent / "origin") or "mit"
            frontmatter = _build_hf_frontmatter(flow, meta, model_name)
            readme.write_text(frontmatter + original, encoding="utf-8")

        # 用 huggingface_hub 上传
        try:
            from huggingface_hub import HfApi, create_repo
            api = HfApi(token=token)
            create_repo(repo_id=repo_id, token=token, exist_ok=True)
            api.upload_folder(
                folder_path=str(hf_dir),
                repo_id=repo_id,
                repo_type="model",
            )
        except ImportError:
            return {"ok": False, "url": public_url,
                    "errors": ["huggingface_hub 未安装，请 pip install huggingface_hub"]}
        except Exception as e:
            return {"ok": False, "url": public_url, "errors": [f"HF 上传失败: {e}"]}

    return {"ok": True, "url": public_url, "errors": []}


def _init_and_push(directory: Path, remote_url: str, commit_msg: str):
    """在目录内初始化 git 并推送。"""
    subprocess.run(["git", "init", "-b", "main"], cwd=str(directory), check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(directory), check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(directory), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(directory), check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=str(directory), check=True, capture_output=True)
