"""LLM 路由判定与 llm_build2 命令生成的单元测试。"""
import json
import tempfile
from pathlib import Path

from magnetar.stages.llm import (
    build_llm_command,
    classify,
    _extract_cosims,
)


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_classify_causal_lm_config():
    with tempfile.TemporaryDirectory() as d:
        origin = Path(d)
        _write_json(origin / "config.json", {
            "architectures": ["Qwen2ForCausalLM"],
            "model_type": "qwen2",
        })
        r = classify(origin, model_name="qwen2-1.5b")
        assert r["route"] == "llm"
        assert r["hybrid"] is False


def test_classify_nested_text_config():
    with tempfile.TemporaryDirectory() as d:
        origin = Path(d)
        _write_json(origin / "config.json", {
            "text_config": {"architectures": ["LlamaForCausalLM"]},
        })
        r = classify(origin)
        assert r["route"] == "llm"


def test_classify_model_card_pipeline_tag():
    with tempfile.TemporaryDirectory() as d:
        origin = Path(d)
        (origin / "README.md").write_text(
            "---\npipeline_tag: text-generation\n---\n# My chat model\n",
            encoding="utf-8")
        r = classify(origin, model_name="my-chat")
        assert r["route"] == "llm"


def test_classify_general_model():
    with tempfile.TemporaryDirectory() as d:
        origin = Path(d)
        _write_json(origin / "config.json", {
            "architectures": ["YOLOv8DetectionModel"],
            "model_type": "yolo",
        })
        r = classify(origin, model_name="yolov8n")
        assert r["route"] == "general"


def test_classify_hybrid_ar_tts():
    with tempfile.TemporaryDirectory() as d:
        origin = Path(d)
        _write_json(origin / "config.json", {
            "architectures": ["Qwen2ForCausalLM"],
        })
        _write_json(origin / "model_flow.json", {"task": "tts"})
        r = classify(origin, model_name="MOSS-TTS-Realtime")
        assert r["route"] == "llm"
        assert r["hybrid"] is True


def test_classify_no_signals():
    with tempfile.TemporaryDirectory() as d:
        origin = Path(d)
        _write_json(origin / "config.json", {"architectures": ["SomeModel"]})
        r = classify(origin)
        assert r["route"] == "general"


def test_build_llm_command():
    cmd = build_llm_command(
        "/workspace/origin/qwen3-0.6B",
        "/workspace/compile/llm_out",
        "AX650",
        max_context=1024,
        prefill_len=512,
        prefill_step_size=128,
        weight_type="s8",
    )
    assert "pulsar2 llm_build2" in cmd
    assert "--chip AX650" in cmd
    assert "--prefill_len 512" in cmd
    assert "--prefill_step_size 128" in cmd
    assert "--max_context 1024" in cmd
    assert "FLOAT_MATMUL_USE_CONV_EU=1" in cmd


def test_extract_cosims():
    log = (
        "decode layer0_gt layer0_got cos_sim is: 1.0\n"
        "prefill layer0_gt layer0_got cos_sim is: 0.995\n"
        "cos_sim: 0.991\n"
    )
    r = _extract_cosims(log)
    assert r["samples"] == 3
    assert r["min"] == 0.991
    assert r["all_ge_0_99"] is True
