"""状态文件（.magnetar-state.json）与编译日志摘要的单元测试。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.export_onnx import ExportError, export_to_onnx  # noqa: E402
from magnetar.stages.compile import summarize_compile_log  # noqa: E402
from magnetar.stages.state import load, mark_stage, save  # noqa: E402


class MagnetarStateTest(unittest.TestCase):
    def test_save_and_mark_stage_merge_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            save(task_dir, model_name="demo")
            mark_stage(task_dir, "EXPORT", artifacts={"onnx": "export/model.onnx"},
                       metrics={"cosine": 0.99}, summary="EXPORT OK")
            mark_stage(task_dir, "COMPILE", artifacts={"axmodel": "compile/model.axmodel"},
                       metrics={"size_kb": 12.3}, summary="COMPILE OK")

            state = load(task_dir)
            self.assertEqual(state["stage"], "COMPILE")
            self.assertEqual(state["artifacts"]["onnx"], "export/model.onnx")
            self.assertEqual(state["artifacts"]["axmodel"], "compile/model.axmodel")
            self.assertEqual(state["metrics"]["cosine"], 0.99)
            self.assertEqual(state["metrics"]["size_kb"], 12.3)
            self.assertIn("updated_at", state)
            self.assertTrue((task_dir / ".magnetar-state.json").is_file())

    def test_export_failure_marks_blocked_and_writes_report(self):
        class Broken(nn.Module):
            def forward(self, x):
                return x.item()

        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            with self.assertRaises(ExportError):
                export_to_onnx(task_dir, model=Broken().eval(), example_inputs=torch.randn(1))
            state = load(task_dir)
            self.assertEqual(state["stage"], "EXPORT")
            self.assertEqual(state["status"], "blocked")
            self.assertTrue((task_dir / "export" / "export_report.md").is_file())

    def test_summarize_compile_log_extracts_metrics_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            compile_dir = task_dir / "compile"
            compile_dir.mkdir(parents=True, exist_ok=True)
            (compile_dir / "compile.log").write_text(
                "start compile\nMACs: 123.45M\nmodel size: 3.2MB\n"
                "ERROR: quantize failed on node Foo\n"
                "[W] something\n"
                "FATAL: build aborted\n",
                encoding="utf-8",
            )
            (compile_dir / "model.axmodel").write_bytes(b"x" * 4096)

            summary = summarize_compile_log(task_dir)
            self.assertEqual(summary["size_bytes"], 4096)
            self.assertIn("123.45", summary["macs"])
            self.assertTrue(any("quantize failed" in e for e in summary["errors"]))
            self.assertTrue(any("FATAL" in e for e in summary["errors"]))
            self.assertLessEqual(len(summary["tail"]), 1500)

    def test_summarize_missing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = summarize_compile_log(Path(tmp))
            self.assertIn("compile.log 不存在", summary["errors"])


if __name__ == "__main__":
    unittest.main()
