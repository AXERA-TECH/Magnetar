"""ACQUIRE: 获取模型权重到本地，并记录模型运行流程（model_flow.json）。"""
import json
import shutil
from pathlib import Path

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
      "verified": true
    }

    SDK 生成时（sdk_gen.run_generic_python/cpp）读取本文件：
    - 模型接口（输入输出名/shape/dtype）以 export/model_meta.json 为权威
    - 预处理/后处理与示例输入以本文件为准，保证与 ACQUIRE 验证过的运行流程一致
    """
    origin = task_dir / "origin"
    origin.mkdir(parents=True, exist_ok=True)
    path = origin / "model_flow.json"
    path.write_text(json.dumps(flow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "ACQUIRE", artifacts={"model_flow": str(path)},
               summary=f"运行流程已记录（verified={flow.get('verified', False)}）")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"- MODEL_FLOW: {path}（verified={flow.get('verified', False)}）\n")
    return path
