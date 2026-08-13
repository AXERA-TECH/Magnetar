"""本机 scratch（TASK_DIR/cache/scratch）与残留扫描的单元测试。"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.scratch import (  # noqa: E402
    cleanup_scratch,
    local_stale_report,
    remove_paths,
    scratch_dir,
)


def _age_dir(path: Path, minutes: int) -> None:
    """把目录 mtime 拨旧，模拟历史残留。"""
    old = time.time() - minutes * 60
    os.utime(path, (old, old))
    for p in path.rglob("*"):
        if p.is_file():
            os.utime(p, (old, old))


class ScratchTest(unittest.TestCase):
    def test_scratch_dir_under_task_and_sanitizes_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = scratch_dir(Path(tmp), "self_test/run 1!")
            self.assertEqual(d, Path(tmp) / "cache" / "scratch" / "self_test" / "run_1_")
            self.assertTrue(d.is_dir())

    def test_cleanup_scratch_removes_children_and_respects_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            a = scratch_dir(task_dir, "self_test")
            b = scratch_dir(task_dir, "serve_cache")
            (a / "x").write_text("x", encoding="utf-8")
            (b / "y").write_text("y", encoding="utf-8")
            removed = cleanup_scratch(task_dir, keep={"serve_cache"})
            self.assertEqual(sorted(removed), [str(a)])
            self.assertTrue(b.is_dir())
            self.assertFalse(a.exists())

    def test_local_stale_report_finds_legacy_tmp_and_finished_task_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "magnetar_pkg_test_old"
            legacy.mkdir()
            (legacy / "model.axmodel").write_bytes(b"x" * 2048)
            _age_dir(legacy, 120)

            done_task = root / "done_task"
            scratch_dir(done_task, "self_test")
            (done_task / ".magnetar-state.json").write_text(
                json.dumps({"stage": "PACKAGE", "status": "done"}), encoding="utf-8")
            _age_dir(done_task / "cache", 30)

            running_task = root / "running_task"
            scratch_dir(running_task, "self_test")
            (running_task / ".magnetar-state.json").write_text(
                json.dumps({"stage": "COMPILE", "status": "running"}), encoding="utf-8")

            report = local_stale_report(tmp_root=root, task_root=root)
            paths = {i["path"] for i in report}
            self.assertIn(str(legacy), paths)
            self.assertIn(str(done_task / "cache" / "scratch"), paths)
            self.assertNotIn(str(running_task / "cache" / "scratch"), paths)
            legacy_item = next(i for i in report if i["path"] == str(legacy))
            self.assertEqual(legacy_item["kind"], "legacy-tmp")
            self.assertGreater(legacy_item["age_min"], 100)
            self.assertGreater(legacy_item["size_mb"], 0)

    def test_remove_paths_tolerates_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "gone"
            f = root / "f.txt"
            f.write_text("x", encoding="utf-8")
            removed = remove_paths([d, f])
            self.assertEqual(set(removed), {str(d), str(f)})
            self.assertFalse(f.exists())


if __name__ == "__main__":
    unittest.main()
