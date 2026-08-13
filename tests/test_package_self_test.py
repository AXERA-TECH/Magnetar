"""PACKAGE self_test 的 scratch 目录行为测试（不再往 /tmp 留垃圾）。"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.scratch import cleanup_scratch, scratch_dir  # noqa: E402
from magnetar.stages.package import self_test  # noqa: E402


def _fake_package(root: Path, run_code: str = "exit 0") -> Path:
    pkg = root / "package"
    pkg.mkdir(parents=True)
    (pkg / "README.md").write_text("# Demo\n", encoding="utf-8")
    (pkg / "setup.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (pkg / "run.sh").write_text(f"#!/usr/bin/env bash\n{run_code}\n", encoding="utf-8")
    return pkg


class PackageSelfTestTest(unittest.TestCase):
    def test_success_cleans_task_scratch(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            pkg = _fake_package(task_dir)
            result = self_test(pkg, task_dir=task_dir)
            self.assertTrue(result["ok"], result["errors"])
            scratch = task_dir / "cache" / "scratch" / "self_test"
            self.assertTrue(scratch.is_dir())  # 目录本身保留
            self.assertEqual(list(scratch.iterdir()), [])  # 但运行子目录已删

    def test_failure_keeps_scratch_for_debugging(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            pkg = _fake_package(task_dir, run_code="exit 3")
            result = self_test(pkg, task_dir=task_dir, keep_on_failure=True)
            self.assertFalse(result["ok"])
            self.assertIn("scratch_dir", result)
            kept = Path(result["scratch_dir"])
            self.assertTrue(kept.is_dir())
            self.assertTrue((kept / "package" / "run.sh").is_file())
            # 任务收尾 cleanup_scratch 可清掉
            cleanup_scratch(task_dir)
            self.assertFalse(kept.exists())

    def test_without_task_dir_always_auto_cleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _fake_package(Path(tmp))
            result = self_test(pkg, keep_on_failure=False)
            self.assertTrue(result["ok"])
            self.assertNotIn("scratch_dir", result)


if __name__ == "__main__":
    unittest.main()
