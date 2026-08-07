"""任务配置隔离测试：TASK_DIR/config.json 快照优先，.magnetarrc 仅公共默认，环境变量最后覆盖。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.config import load_task_config  # noqa: E402


class TaskConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".magnetarrc").write_text(
            "SOURCE=global\nTARGET_HARDWARE=AX650\nHF_ENDPOINT=https://hf-mirror.com\n",
            encoding="utf-8",
        )
        self.task = self.root / "tasks" / "task_a"
        self.task.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_wins_over_global_rc(self):
        (self.task / "config.json").write_text(
            json.dumps({"SOURCE": "task_a", "TARGET_HARDWARE": "AX630C"}),
            encoding="utf-8",
        )
        cfg = load_task_config(self.task, project_root=self.root)
        self.assertEqual(cfg["SOURCE"], "task_a")
        self.assertEqual(cfg["TARGET_HARDWARE"], "AX630C")
        # 全局 rc 里任务没有覆盖的键仍回退
        self.assertEqual(cfg["HF_ENDPOINT"], "https://hf-mirror.com")
        self.assertEqual(cfg["TASK_DIR"], str(self.task))

    def test_env_overrides_snapshot(self):
        (self.task / "config.json").write_text(
            json.dumps({"SOURCE": "snapshot_src"}),
            encoding="utf-8",
        )
        old = os.environ.get("SOURCE")
        os.environ["SOURCE"] = "env_src"
        try:
            cfg = load_task_config(self.task, project_root=self.root)
            self.assertEqual(cfg["SOURCE"], "env_src")
        finally:
            if old is None:
                os.environ.pop("SOURCE", None)
            else:
                os.environ["SOURCE"] = old

    def test_no_snapshot_falls_back_to_global(self):
        cfg = load_task_config(self.task, project_root=self.root)
        self.assertEqual(cfg["SOURCE"], "global")


if __name__ == "__main__":
    unittest.main()
