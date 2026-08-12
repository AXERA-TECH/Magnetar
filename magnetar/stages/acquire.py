"""ACQUIRE: 获取模型权重到本地，并记录模型运行流程（model_flow.json）。"""
import json
import re
import shutil
from pathlib import Path


_LICENSE_FILE_NAMES = (
    "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE-MIT", "LICENSE-APACHE",
    "COPYING", "COPYING.md", "COPYING.txt",
)
_SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.\-]+)")
# 已知许可证特征串（按优先级匹配；全部命中才算）
_KNOWN_LICENSES = [
    ("mit", ("permission is hereby granted, free of charge",)),
    ("apache-2.0", ("apache license", "version 2.0")),
    ("bsd-3-clause", ("redistribution and use in source and binary forms", "neither the name")),
    ("bsd-2-clause", ("redistribution and use in source and binary forms",)),
    ("gpl-3.0", ("gnu general public license", "version 3")),
    ("gpl-2.0", ("gnu general public license", "version 2")),
    ("lgpl-3.0", ("gnu lesser general public license",)),
    ("cc-by-4.0", ("creative commons attribution 4.0",)),
    ("cc-by-nc-4.0", ("creative commons attribution-noncommercial 4.0",)),
    ("cc0-1.0", ("cc0 1.0",)),
]


def infer_source_license(origin: Path) -> str:
    """从 ACQUIRE 得到的源仓库扫描 LICENSE 文件，推断 SPDX license id。

    优先 ``SPDX-License-Identifier`` 行，其次按许可证正文特征匹配；
    找不到返回空串（调用方自行决定默认值）。
    """
    if not origin.is_dir():
        return ""
    candidates = [origin, *sorted(p for p in origin.iterdir() if p.is_dir())]
    for base in candidates:
        for name in _LICENSE_FILE_NAMES:
            p = base / name
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")[:20000]
            m = _SPDX_RE.search(text)
            if m:
                return m.group(1).lower()
            low = text.lower()
            for lic, markers in _KNOWN_LICENSES:
                if all(marker in low for marker in markers):
                    return lic
    return ""


def run(task_dir: Path, source: str) -> Path:
    origin = task_dir / "origin"; origin.mkdir(parents=True, exist_ok=True)
    sp = Path(source).expanduser().resolve()
    if sp.exists():
        if sp.is_dir(): shutil.copytree(sp, origin / sp.name, dirs_exist_ok=True)
        else: shutil.copy2(sp, origin / sp.name)
        detail = f"Local: {sp}"
    else:
        (origin / "source.txt").write_text(source, encoding="utf-8")
        detail = f"Remote: {source}"
    (origin / "ACQUIRE_REPORT.md").write_text(f"# ACQUIRE Report\n\n- Source: {detail}\n", encoding="utf-8")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f: f.write(f"\n- ACQUIRE: {detail}\n")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "ACQUIRE", artifacts={"origin": str(origin)}, summary=f"ACQUIRE {detail[:120]}")
    return origin


def write_model_flow(task_dir: Path, flow: dict) -> Path:
    """记录模型运行流程，保证后续 SDK 与 ACQUIRE 阶段验证过的流程一致。

    flow 字段约定（Agent 在 ACQUIRE 阶段基于实际拿到的模型填写并调用本函数）：
    {
      "model_name": "demo",
      "framework": "pytorch | tensorflow | onnx | ...",
      "source": "来源描述",
      "example_input": "真实样本路径（相对 TASK_DIR 或绝对路径；缺省用 export/sample_input.npy）",
      "preprocess_code": "可选：Python 代码，定义 preprocess(*arrays) -> list（原始输入到模型输入）",
      "postprocess_code": "可选：Python 代码，定义 postprocess(*arrays) -> 结果（模型输出到用户结果）",
      "preprocess_note": "预处理说明（resize/归一化等），写入 SDK README",
      "postprocess_note": "后处理说明（topk/解码等），写入 SDK README",
      "sdk_interface": "可选：原版模型调用约定 {'entry': '函数/方法名', 'args': '入参顺序与格式', 'returns': '输出结构'}，SDK 示例尽量镜像原版入口",
      "task": "可选：任务类型（tts/asr/llm/detection/classification...），HF 发布推断 pipeline_tag 用",
      "license": "可选：SPDX license id；缺省由 ACQUIRE 源仓库 LICENSE 推断，推断不到用 mit",
      "verified": true
    }

    SDK 生成时（sdk_gen.run_generic_python/cpp）读取本文件：
    - 模型接口（输入输出名/shape/dtype）以 export/model_meta.json 为权威
    - 预处理/后处理与示例输入以本文件为准，保证与 ACQUIRE 验证过的运行流程一致
    - 前后处理必须对齐原版模型管线（preprocess_code/postprocess_code 来自原版实现），
      调用方式尽量对齐原版入口（sdk_interface），不得为省事改成直通/自定义
    """
    origin = task_dir / "origin"
    origin.mkdir(parents=True, exist_ok=True)
    flow = dict(flow)
    if not flow.get("license"):
        flow["license"] = infer_source_license(origin) or "mit"
    path = origin / "model_flow.json"
    path.write_text(json.dumps(flow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "ACQUIRE", artifacts={"model_flow": str(path)},
               summary=f"运行流程已记录（verified={flow.get('verified', False)}）")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"- MODEL_FLOW: {path}（verified={flow.get('verified', False)}）\n")
    return path
