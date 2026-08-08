"""LLM / 自回归模型路由与 ax-llm 部署工具。

当模型被判定为自回归或类 LLM（causal LM / chat 模型 / 含 LLM 骨干的 TTS）时，
不走 ``ONNX 导出 -> pulsar2 build`` 的通用路径，而是：

1. COMPILE 用 Pulsar2 ``llm_build2`` 直接吃 HuggingFace 权重，产出逐层 axmodel +
   post axmodel + bf16 embedding（自带逐层 decode/prefill cosine 校验）；
2. 板端用 AXERA-TECH/ax-llm（axllm 分支，可执行文件名 ``axllm``）运行/服务；
3. SDK 为 OpenAI 兼容 HTTP 客户端（``axllm serve``），不再依赖 pyaxengine。

主要函数：

- ``classify()``：模型路由判定（llm / general，hybrid 标记含 LLM 子模型的组合模型）
- ``build_llm_command()``：生成可复现的 ``pulsar2 llm_build2`` 命令（纯函数）
- ``llm_build()``：执行编译 + embedding 处理 + axllm config/meta/report 产出
- ``install_axllm()`` / ``serve_axllm()`` / ``stop_serve()`` / ``validate_chat()``：
  板端 axllm 安装、启动、停止与 OpenAI 兼容接口语义验证
"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

AX_LLM_REPO = "https://github.com/AXERA-TECH/ax-llm.git"
AX_LLM_BRANCH = "axllm"
AX_LLM_BUILD_REPO = "https://github.com/AXERA-TECH/ax-llm-build.git"
AXLLM_INSTALL_URL = (
    "https://raw.githubusercontent.com/AXERA-TECH/ax-llm/axllm/install.sh"
)

# ---------------------------------------------------------------------------
# 路由判定
# ---------------------------------------------------------------------------

CAUSAL_SUFFIXES = (
    "forcausallm", "lmheadmodel", "chatmodel", "causallm", "modelwithkv",
)
KNOWN_LLM_MODEL_TYPES = {
    "qwen", "qwen2", "qwen2.5", "qwen3", "qwen3.5",
    "llama", "llama2", "llama3", "gemma", "gemma2", "gemma3",
    "mistral", "phi", "phi3", "minicpm", "smollm", "smollm2",
    "gpt2", "gpt_neo", "gpt_neox", "gptj", "mpt", "falcon", "opt",
    "bloom", "chatglm", "deepseek", "internlm", "baichuan", "starcoder2",
    "moss", "stablelm", "xverse", "yi", "cohere", "command-r", "olmo",
}
LLM_NAME_HINTS = (
    "llm", "chat", "gpt", "qwen", "llama", "deepseek", "minicpm",
    "smollm", "mistral", "gemma", "internlm", "baichuan", "moonshot",
    "kimi", "glm", "olmo", "falcon", "starcoder", "instruct", "generation",
)
# 组合模型：整体是 TTS/多子模型，但包含 LLM/AR 骨干（如 MOSS-TTS、NeuTTS-2E），
# 需要拆分：LLM/AR 子模型走 ax-llm，其余子模型走通用 ONNX 路径。
HYBRID_LLM_HINTS = ("moss", "neutt", "valle", "cosyvoice", "audio8")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_config(origin: Path) -> Path | None:
    """在 origin 下定位 HuggingFace config.json（含嵌套 text_config 的模型）。"""
    for p in [origin / "config.json", origin / "text_config.json"]:
        if p.is_file():
            return p
    hits = sorted(origin.rglob("config.json"))
    if hits:
        return hits[0]
    return None


def _deep_get(cfg: dict, key: str, depth: int = 2) -> list:
    """递归收集 cfg 中所有名为 key 的值（最多 depth 层，用于 text_config 嵌套）。"""
    out: list = []

    def walk(node, level):
        if not isinstance(node, dict) or level > depth:
            return
        for k, v in node.items():
            if k == key:
                if isinstance(v, list):
                    out.extend(v)
                else:
                    out.append(v)
            walk(v, level + 1)

    walk(cfg, 0)
    return out


def _model_card_pipeline_tags(origin: Path) -> list[str]:
    tags = []
    readme = origin / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8", errors="ignore")[:8000]
        m = re.search(r"(?m)^pipeline_tag\s*:\s*(\S+)", text)
        if m:
            tags.append(m.group(1).strip().strip('"').strip("'"))
        m = re.search(r'"pipeline_tag"\s*:\s*"([^"]+)"', text)
        if m:
            tags.append(m.group(1))
    return tags


def classify(origin: Path, *, source: str = "", model_name: str = "",
             manifest: dict | None = None) -> dict:
    """判定模型路由。

    Returns:
        {"route": "llm"|"general", "hybrid": bool, "reason": str,
         "signals": [str], "llm_submodel": str|None}
    """
    origin = Path(origin)
    signals: list[str] = []
    cfg_path = _find_config(origin)
    cfg = _read_json(cfg_path) if cfg_path else {}

    archs = [str(a).lower() for a in _deep_get(cfg, "architectures")]
    model_types = [str(t).lower() for t in _deep_get(cfg, "model_type")]
    text_archs = [str(a).lower() for a in _deep_get(cfg.get("text_config", {}), "architectures")]

    for a in archs + text_archs:
        if any(a.endswith(s) or s in a for s in CAUSAL_SUFFIXES):
            signals.append(f"config architectures: {a}")
            break
    for t in model_types:
        if t in KNOWN_LLM_MODEL_TYPES or "causal" in t or "llm" in t:
            signals.append(f"config model_type: {t}")
            break

    tags = _model_card_pipeline_tags(origin)
    if "text-generation" in tags or "text_generation" in tags:
        signals.append(f"model card pipeline_tag: {tags}")

    flow_task = ""
    flow_path = origin / "model_flow.json"
    if flow_path.is_file():
        flow = _read_json(flow_path)
        flow_task = str(flow.get("task", "")).lower()
        if flow_task in {"text_generation", "causal_lm", "chat", "llm", "chat_completion"}:
            signals.append(f"model_flow task: {flow_task}")

    text = f"{source} {model_name}".lower()
    name_hits = [h for h in LLM_NAME_HINTS if h in text]
    hybrid_hits = [h for h in HYBRID_LLM_HINTS if h in text]

    if manifest:
        mcfg = manifest.get("route_hint", {})
        if mcfg.get("llm"):
            signals.append(f"ACQUIRE route_hint: {mcfg.get('reason', '')}")

    hybrid = bool(hybrid_hits) and bool(signals)
    if not hybrid and hybrid_hits:
        signals.append(f"known LLM/AR hybrid name hint: {hybrid_hits}")

    is_llm = bool(signals)
    if is_llm and not hybrid and name_hits:
        signals.append(f"name/source hint: {name_hits}")
    elif not is_llm and name_hits:
        signals.append(f"weak name/source hint only: {name_hits}")

    if is_llm:
        return {
            "route": "llm",
            "hybrid": hybrid,
            "reason": "; ".join(signals),
            "signals": signals,
            "llm_submodel": _guess_llm_submodel(origin),
        }
    return {
        "route": "general",
        "hybrid": False,
        "reason": "; ".join(signals) if signals else "无 LLM/自回归特征，走通用 ONNX 路径",
        "signals": signals,
        "llm_submodel": None,
    }


def _guess_llm_submodel(origin: Path) -> str | None:
    """组合模型（如 MOSS-TTS）中猜测 LLM/AR 子模型目录；无把握返回 None。"""
    for sub in sorted(origin.iterdir()) if origin.is_dir() else []:
        if sub.is_dir() and (sub / "config.json").is_file():
            c = _read_json(sub / "config.json")
            archs = [str(a).lower() for a in _deep_get(c, "architectures")]
            if any(any(a.endswith(s) or s in a for s in CAUSAL_SUFFIXES) for a in archs):
                return sub.name
    return None


# ---------------------------------------------------------------------------
# pulsar2 llm_build2
# ---------------------------------------------------------------------------


def build_llm_command(input_rel: str, output_rel: str, chip: str,
                      *, max_context: int = 1024, prefill_len: int = 0,
                      prefill_step_size: int | None = None,
                      decode_step_size: int | None = None,
                      hidden_state_type: str = "bf16", weight_type: str = "s8",
                      parallel: int = 8, check_level: int = 0,
                      prompt: str | None = None,
                      model_config: str | None = None,
                      model_type: str | None = None) -> str:
    """生成可复现的 llm_build2 命令（/workspace 相对路径，供 Docker 内执行）。"""
    args = [
        "FLOAT_MATMUL_USE_CONV_EU=1",
        "pulsar2", "llm_build2",
        "--input_path", input_rel,
        "--output_path", output_rel,
        "--chip", chip,
        "--max_context", str(max_context),
        "--hidden_state_type", hidden_state_type,
        "--weight_type", weight_type,
        "--parallel", str(parallel),
        "--check_level", str(check_level),
    ]
    if prefill_len:
        args += ["--prefill_len", str(prefill_len)]
    if prefill_step_size:
        args += ["--prefill_step_size", str(prefill_step_size)]
    if decode_step_size:
        args += ["--decode_step_size", str(decode_step_size)]
    if prompt:
        args += ["--prompt", f'"{prompt}"']
    if model_config:
        args += ["--model_config", model_config]
    if model_type:
        args += ["--model_type", model_type]
    return " ".join(args)


def _run_docker(image: str, workspace: str, command: str, timeout: int,
                log_file: Path):
    from magnetar.docker_util import docker_pulsar2
    return docker_pulsar2(image, workspace, command, timeout=timeout,
                          log_file=log_file, max_tail=400)


def ensure_axllm_build_tools(task_dir: Path) -> Path:
    """克隆 ax-llm-build 到 cache/ax-llm-build（embed 处理工具），返回目录。"""
    cache = task_dir / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    tools = cache / "ax-llm-build"
    if not (tools / "tools" / "embed_process.sh").is_file():
        subprocess.run(
            ["git", "clone", "--depth=1", AX_LLM_BUILD_REPO, str(tools)],
            check=True, timeout=600,
        )
    for name in ("fp32_to_bf16", "embed_process.sh", "extract_embed.py",
                 "embed-process.py"):
        p = tools / "tools" / name
        if p.is_file():
            p.chmod(0o755)
    return tools


def _process_embedding(tools: Path, input_host: Path, output_host: Path):
    """运行 ax-llm-build 的 embed_process.sh 提取并转换 embedding 为 bf16。"""
    script = tools / "tools" / "embed_process.sh"
    if not script.is_file():
        raise FileNotFoundError(f"缺少 {script}，请确认 ax-llm-build 已克隆")
    subprocess.run(
        ["bash", str(script), str(input_host), str(output_host)],
        cwd=tools, check=True, timeout=1800,
    )


def _derive_axllm_config(model_dir: Path, hf_cfg: dict,
                         tokenizer_type: str | None) -> dict:
    """根据 llm_build2 产物与 HF config 生成 axllm config.json。"""
    layers = [p for p in model_dir.glob("*_l*_*.axmodel")]
    posts = [p for p in model_dir.glob("*post*.axmodel")]
    if not layers:
        raise FileNotFoundError(f"{model_dir} 下未找到逐层 axmodel（*_l*_*.axmodel）")
    if not posts:
        raise FileNotFoundError(f"{model_dir} 下未找到 post axmodel（*post*.axmodel）")

    template = re.sub(r"l\d+", "l%d", layers[0].name)
    if "%d" not in template:
        template = re.sub(r"(\d+)", "%d", template, count=1)

    hidden_size = hf_cfg.get("hidden_size") or hf_cfg.get("d_model")
    vocab = hf_cfg.get("vocab_size")
    if not hidden_size:
        for v in _deep_get(hf_cfg, "hidden_size"):
            hidden_size = v
            break
    if not vocab:
        for v in _deep_get(hf_cfg, "vocab_size"):
            vocab = v
            break
    if not hidden_size or not vocab:
        raise ValueError(
            f"HF config.json 缺少 hidden_size/vocab_size（当前 {hf_cfg}），"
            "无法生成 axllm config.json，请检查模型目录"
        )

    model_type = str(hf_cfg.get("model_type", "")).replace("-", "")
    tokenizer_type = tokenizer_type or model_type or "llm"
    tokenizer_file = next(
        (p.name for p in model_dir.glob("*tokenizer*.txt")),
        "tokenizer.txt",
    )
    cfg = {
        "model_name": str(hf_cfg.get("_name_or_path") or hf_cfg.get("model_type") or "llm"),
        "tokenizer_type": tokenizer_type,
        "url_tokenizer_model": tokenizer_file,
        "template_filename_axmodel": template,
        "axmodel_num": len(layers),
        "filename_post_axmodel": posts[0].name,
        "filename_tokens_embed": "model.embed_tokens.weight.bfloat16.bin",
        "tokens_embed_num": int(vocab),
        "tokens_embed_size": int(hidden_size),
    }
    # 长上下文/混合注意力可选字段透传
    for k in ("full_attention_interval", "num_kv_shared_layers",
              "sliding_window", "layer_types", "kv_cache_slots",
              "is_embedding", "vlm_type", "filename_image_encoder_axmodel"):
        if hf_cfg.get(k) is not None:
            cfg[k] = hf_cfg[k]
    return cfg


def _extract_cosims(log: str) -> dict:
    """从 llm_build2 日志提取逐层 cosine（decode/prefill 自带校验）。"""
    cos = re.findall(r"cos[_ ]sim\s*(?:is)?\s*[:=]?\s*([01](?:\.\d+)?)", log)
    nums = [float(x) for x in cos]
    return {
        "samples": len(nums),
        "min": min(nums) if nums else None,
        "mean": round(sum(nums) / len(nums), 6) if nums else None,
        "all_ge_0_99": bool(nums) and all(x >= 0.99 for x in nums),
    }


def llm_build(task_dir: Path, input_path: Path, chip: str = "AX650",
              pulsar_image: str | None = None, *,
              max_context: int = 1024, prefill_len: int = 0,
              prefill_step_size: int | None = None,
              decode_step_size: int | None = None,
              hidden_state_type: str = "bf16", weight_type: str = "s8",
              parallel: int = 8, check_level: int = 0, prompt: str | None = None,
              tokenizer_txt: Path | None = None,
              tokenizer_type: str | None = None) -> Path:
    """LLM 路由的 COMPILE：pulsar2 llm_build2 + embedding 处理 + axllm 模型目录。

    Returns: compile/llm_model_dir（板端 axllm run/serve 的模型目录）。
    同时产出 export/model_meta.json（LLM 版）、compile/compile_report.md、
    export/llm_build.sh（可复现脚本）。
    """
    from magnetar.docker_util import latest_pulsar2_image
    from magnetar.stages.state import mark_stage

    task_dir = Path(task_dir)
    compile_dir = task_dir / "compile"
    compile_dir.mkdir(parents=True, exist_ok=True)
    input_host = Path(input_path).resolve()
    if not str(input_host).startswith(str(task_dir.resolve())):
        raise ValueError(f"llm_build input 必须在 TASK_DIR 内: {input_host}")
    input_rel = str(input_host.relative_to(task_dir.resolve()))

    out_dir = compile_dir / "llm_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_rel = "compile/llm_out"

    image = pulsar_image or latest_pulsar2_image()
    cmd = build_llm_command(
        f"/workspace/{input_rel}", f"/workspace/{output_rel}", chip,
        max_context=max_context, prefill_len=prefill_len,
        prefill_step_size=prefill_step_size,
        decode_step_size=decode_step_size,
        hidden_state_type=hidden_state_type, weight_type=weight_type,
        parallel=parallel, check_level=check_level, prompt=prompt,
    )
    log_file = compile_dir / "llm_build.log"
    _run_docker(image, str(task_dir), cmd, timeout=10800, log_file=log_file)

    tools = ensure_axllm_build_tools(task_dir)
    _process_embedding(tools, input_host, out_dir)

    model_dir = compile_dir / "llm_model_dir"
    model_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.axmodel"):
        shutil.copy2(f, model_dir / f.name)
    embed_bin = out_dir / "model.embed_tokens.weight.bfloat16.bin"
    if embed_bin.is_file():
        shutil.copy2(embed_bin, model_dir / embed_bin.name)

    # tokenizer：优先参数指定，其次 origin/out 中现成 tokenizer.txt
    tok = tokenizer_txt
    if tok is None:
        for p in [task_dir / "origin", out_dir]:
            hits = list(p.rglob("tokenizer.txt")) + list(p.rglob("*_tokenizer.txt"))
            if hits:
                tok = hits[0]
                break
    if tok is None:
        raise FileNotFoundError(
            "未找到 axllm tokenizer 文件（tokenizer.txt / *_tokenizer.txt）。"
            "请按 ax-llm 文档生成 tokenizer 后重试（参数 tokenizer_txt=...）。"
        )
    shutil.copy2(tok, model_dir / Path(tok).name)

    # hybrid 模型时 input_path 指向 LLM/AR 子模型目录，优先用其自身 config.json
    hf_cfg_path = (input_host / "config.json"
                   if (input_host / "config.json").is_file()
                   else _find_config(task_dir / "origin"))
    hf_cfg = _read_json(hf_cfg_path) if Path(hf_cfg_path).is_file() else {}
    axllm_cfg = _derive_axllm_config(model_dir, hf_cfg, tokenizer_type)
    (model_dir / "config.json").write_text(
        json.dumps(axllm_cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    post_cfg = {
        "enable_temperature": False, "temperature": 1.0,
        "enable_top_k_sampling": False, "top_k": 1,
        "enable_top_p_sampling": False, "top_p": 1.0,
        "enable_repetition_penalty": False, "repetition_penalty": 1.2,
        "penalty_window": 20,
    }
    (model_dir / "post_config.json").write_text(
        json.dumps(post_cfg, indent=2), encoding="utf-8")

    log_text = (
        log_file.read_text(encoding="utf-8", errors="ignore")
        if log_file.is_file() else ""
    )
    cos = _extract_cosims(log_text)
    meta = {
        "model_name": axllm_cfg["model_name"],
        "framework": "pytorch",
        "route": "llm",
        "chip": chip,
        "build": {
            "max_context": max_context, "prefill_len": prefill_len,
            "prefill_step_size": prefill_step_size,
            "decode_step_size": decode_step_size,
            "hidden_state_type": hidden_state_type,
            "weight_type": weight_type, "parallel": parallel,
        },
        "axllm_config": axllm_cfg,
        "model_dir": str(model_dir),
        "layer_axmodels": [p.name for p in sorted(model_dir.glob("*_l*_*.axmodel"))],
        "post_axmodel": axllm_cfg["filename_post_axmodel"],
        "embedding_bin": axllm_cfg["filename_tokens_embed"],
        "tokenizer_file": axllm_cfg["url_tokenizer_model"],
        "compile_cosine": cos,
        "pipeline": "pulsar2 llm_build2 + axllm",
    }
    (task_dir / "export").mkdir(exist_ok=True)
    (task_dir / "export" / "model_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.copy2(task_dir / "export" / "model_meta.json", model_dir / "model_meta.json")

    (task_dir / "export" / "llm_build.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "# 可复现的 LLM 编译命令（在 TASK_DIR 根目录执行）\n"
        f"cd \"$(dirname \"$0\")/..\"\n"
        f"docker run --rm -v \"$PWD\":/workspace {image} -lc '{cmd}'\n",
        encoding="utf-8")
    (task_dir / "export" / "llm_build.sh").chmod(0o755)

    (compile_dir / "compile_report.md").write_text(
        "# LLM Compile Report\n\n"
        f"- image: {image}\n- chip: {chip}\n"
        f"- weight_type: {weight_type}, hidden_state_type: {hidden_state_type}\n"
        f"- max_context: {max_context}, prefill_len: {prefill_len}, "
        f"prefill_step_size: {prefill_step_size or 'auto'}\n"
        f"- llm_build2 自带校验 cosine: {cos}\n"
        f"- 产物目录: {model_dir}\n- 完整日志: {log_file}\n",
        encoding="utf-8")
    mark_stage(
        task_dir, "COMPILE",
        artifacts={"axmodel_dir": str(model_dir)},
        metrics={**cos, "weight_type": weight_type, "max_context": max_context},
        summary=f"llm_build2 完成（{len(meta['layer_axmodels'])} 层，cosine {cos.get('mean')}）",
    )
    return model_dir


# ---------------------------------------------------------------------------
# 板端 axllm
# ---------------------------------------------------------------------------


def install_axllm(board: dict, timeout: int = 1800) -> str:
    """确保板端 axllm 可用；缺失时用官方 install.sh 安装，返回版本输出。"""
    from magnetar.board_util import ssh
    repo = os.environ.get("AX_LLM_REPO", AX_LLM_REPO)
    branch = os.environ.get("AX_LLM_BRANCH", AX_LLM_BRANCH)
    install_url = os.environ.get("AXLLM_INSTALL_URL") or (
        f"https://raw.githubusercontent.com/{repo.split('github.com/')[-1]}/{branch}/install.sh"
        if "github.com" in repo else AXLLM_INSTALL_URL
    )
    try:
        out = ssh(board, "which axllm && axllm --help 2>&1 | head -3", 30)
        return out
    except RuntimeError:
        pass
    ssh(board, f"curl -fsSL {install_url} | bash", timeout=timeout, max_tail=200)
    return ssh(board, "axllm --help 2>&1 | head -3", 30)


def serve_axllm(board: dict, model_dir: Path, port: int = 8000,
                remote_root: str | None = None) -> str:
    """上传 LLM 模型目录并启动 axllm serve，返回远端模型目录路径。"""
    from magnetar.board_util import scp_to, ssh
    rd = remote_root or f"/tmp/magnetar_llm_{int(time.time())}"
    ssh(board, f"rm -rf {rd} && mkdir -p {rd}", 30)
    scp_to(board, model_dir, f"{rd}/model")
    ssh(board, f"mkdir -p {rd}/model && mv {rd}/model/* {rd}/model/ 2>/dev/null || true", 30)
    ssh(board, f"nohup axllm serve {rd}/model --port {port} > {rd}/serve.log 2>&1 & echo $!", 30)
    deadline = time.time() + 180
    while time.time() < deadline:
        ok = ssh(
            board,
            f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/health || true",
            20,
        )
        if ok.strip() == "200":
            return f"{rd}/model"
        time.sleep(3)
    log = ssh(board, f"tail -100 {rd}/serve.log", 30, max_tail=100)
    raise RuntimeError(f"axllm serve 未就绪（{port}）:\n{log}")


def stop_serve(board: dict):
    from magnetar.board_util import ssh
    ssh(board, "pkill -f 'axllm serve' || true", 30)


def validate_chat(api_url: str, model_name: str, prompts: list[str],
                  expected_keyword: str | None = None) -> dict:
    """通过 OpenAI 兼容接口验证生成质量（greedy，便于复现）。

    Returns: {"prompts": int, "ok": bool, "responses": [{...}], "metrics": {...}}
    """
    import requests
    results = []
    for p in prompts:
        t0 = time.time()
        r = requests.post(
            f"{api_url}/v1/chat/completions",
            json={"model": model_name, "messages": [{"role": "user", "content": p}],
                  "temperature": 0, "max_tokens": 128},
            timeout=300,
        )
        r.raise_for_status()
        body = r.json()
        content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = body.get("usage", {})
        results.append({
            "prompt": p,
            "response_len": len(content),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "elapsed_s": round(time.time() - t0, 3),
            "snippet": content[:80],
            "keyword_hit": bool(expected_keyword and expected_keyword in content),
        })
    ok = all(r["response_len"] > 0 for r in results)
    if expected_keyword:
        ok = ok and all(r["keyword_hit"] for r in results)
    metrics = {
        "prompts": len(prompts),
        "avg_completion_tokens": round(
            sum(r["completion_tokens"] or 0 for r in results) / len(results), 1),
        "avg_elapsed_s": round(sum(r["elapsed_s"] for r in results) / len(results), 3),
        "all_non_empty": ok,
    }
    return {"prompts": len(prompts), "ok": ok, "responses": results, "metrics": metrics}
