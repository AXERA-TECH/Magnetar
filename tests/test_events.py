"""每任务 JSONL 事件日志（.magnetar-events.jsonl）的单元测试。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.errors import MagnetarError  # noqa: E402
from magnetar.stages.events import EVENT_LOG_NAME, log_error, log_event  # noqa: E402
from magnetar.stages.state import mark_stage  # noqa: E402


def read_events(task_dir: Path) -> list[dict]:
    path = task_dir / EVENT_LOG_NAME
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class EventsTest(unittest.TestCase):
    def test_mark_stage_writes_stage_artifact_metric_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            mark_stage(task_dir, "EXPORT", artifacts={"onnx": "export/model.onnx"},
                       metrics={"cosine": 0.99}, summary="EXPORT OK")
            events = read_events(task_dir)
            types = [e["type"] for e in events]
            self.assertEqual(types[0], "task/start")  # 首次写入自动补任务启动事件
            self.assertIn("stage/done", types)
            done = next(e for e in events if e["type"] == "stage/done")
            self.assertEqual(done["stage"], "EXPORT")
            self.assertEqual(done["summary"], "EXPORT OK")
            art = next(e for e in events if e["type"] == "artifact/created")
            self.assertEqual((art["key"], art["path"]), ("onnx", "export/model.onnx"))
            metric = next(e for e in events if e["type"] == "metric/recorded")
            self.assertEqual((metric["key"], metric["value"]), ("cosine", 0.99))

    def test_mark_stage_dedups_same_keys_and_logs_new_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            mark_stage(task_dir, "EXPORT", artifacts={"onnx": "export/model.onnx"})
            mark_stage(task_dir, "EXPORT", artifacts={"onnx": "export/model.onnx"},
                       metrics={"size_kb": 1.5})
            mark_stage(task_dir, "COMPILE", artifacts={"axmodel": "compile/model.axmodel"})
            artifacts = [e for e in read_events(task_dir) if e["type"] == "artifact/created"]
            self.assertEqual([(e["key"], e["path"]) for e in artifacts],
                             [("onnx", "export/model.onnx"), ("axmodel", "compile/model.axmodel")])
            metrics = [e for e in read_events(task_dir) if e["type"] == "metric/recorded"]
            self.assertEqual([e["key"] for e in metrics], ["size_kb"])

    def test_mark_stage_blocked_and_skipped_event_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            mark_stage(task_dir, "COMPILE", status="blocked", summary="见日志")
            mark_stage(task_dir, "RUNONBOARD", status="skipped", summary="BOARD 未配置")
            types = [e["type"] for e in read_events(task_dir)]
            self.assertIn("stage/blocked", types)
            self.assertIn("stage/skipped", types)

    def test_log_event_rejects_unknown_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                log_event(Path(tmp), "no/such/event")

    def test_log_error_classifies_wrapped_magnetar_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            try:
                try:
                    raise MagnetarError("ssh_transient", "board unreachable")
                except MagnetarError as e:
                    raise RuntimeError("ssh call failed") from e
            except RuntimeError as outer:
                code = log_error(task_dir, outer, stage="RUNONBOARD")
            self.assertEqual(code, "ssh_transient")
            event = read_events(task_dir)[0]
            self.assertEqual(event["type"], "error/raised")
            self.assertEqual(event["code"], "ssh_transient")
            self.assertEqual(event["stage"], "RUNONBOARD")


if __name__ == "__main__":
    unittest.main()
