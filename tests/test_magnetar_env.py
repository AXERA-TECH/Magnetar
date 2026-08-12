"""共享 base venv + 任务薄 venv 复用逻辑测试（mock 安装，不做真实下载）。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import magnetar.env_util as env_util  # noqa: E402


class EnvUtilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="magnetar_env_test_"))

    def _fake_base(self):
        venv = self.tmp / "base-venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").touch()
        return venv

    def test_req_hash_stable(self):
        self.assertEqual(env_util._req_hash(), env_util._req_hash())

    def test_ensure_base_skips_when_marker_matches(self):
        venv = self._fake_base()
        env_util._marker(venv).write_text(env_util._req_hash(), encoding="utf-8")
        with mock.patch.dict(os.environ, {"MAGNETAR_BASE_VENV": str(venv)}), \
             mock.patch.object(env_util, "_run") as run:
            got = env_util.ensure_base_env()
        self.assertEqual(got, venv)
        run.assert_not_called()

    def test_ensure_base_rebuilds_on_marker_change(self):
        venv = self._fake_base()
        env_util._marker(venv).write_text("old-hash", encoding="utf-8")
        with mock.patch.dict(os.environ, {"MAGNETAR_BASE_VENV": str(venv)}), \
             mock.patch.object(env_util, "_run") as run:
            env_util.ensure_base_env()
        cmds = [c.args[0] for c in run.call_args_list]
        self.assertTrue(any(c[0] == "uv" and "venv" in c for c in cmds))
        self.assertTrue(any("torch" in c for c in cmds))
        self.assertTrue(any("-r" in c and any("base.txt" in s for s in c) for c in cmds))
        self.assertEqual(
            env_util._marker(venv).read_text(encoding="utf-8"),
            env_util._req_hash(),
        )

    def test_create_task_venv_system_site_packages_and_config(self):
        base = self._fake_base()
        task = self.tmp / "task"
        task.mkdir()
        with mock.patch.object(env_util, "ensure_base_env", return_value=base), \
             mock.patch.object(env_util, "_run") as run, \
             mock.patch.object(env_util, "_py_output", side_effect=[
                 str(base / "lib" / "python3.10" / "site-packages"),
                 str(task / ".venv" / "lib" / "python3.10" / "site-packages"),
             ]):
            venv = env_util.create_task_venv(task, extra_packages=("sentencepiece",))
        self.assertEqual(venv, task / ".venv")
        cmds = [c.args[0] for c in run.call_args_list]
        self.assertTrue(any("sentencepiece" in c for c in cmds))
        cfg = json.loads((task / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["VENV_PATH"], str(task / ".venv"))
        pth = task / ".venv" / "lib" / "python3.10" / "site-packages" / "_magnetar_base.pth"
        self.assertEqual(
            pth.read_text(encoding="utf-8").strip(),
            str(base / "lib" / "python3.10" / "site-packages"),
        )

    def test_resolve_task_python_prefers_task_venv(self):
        base = self._fake_base()
        task = self.tmp / "task"
        (task / ".venv" / "bin").mkdir(parents=True)
        (task / ".venv" / "bin" / "python").touch()
        (task / "config.json").write_text(
            json.dumps({"VENV_PATH": str(task / ".venv")}), encoding="utf-8")
        with mock.patch.object(env_util, "base_env_dir", return_value=base):
            self.assertEqual(env_util.resolve_task_python(task),
                             str(task / ".venv" / "bin" / "python"))

    def test_resolve_task_python_falls_back_to_base(self):
        base = self._fake_base()
        task = self.tmp / "task"
        task.mkdir()
        with mock.patch.object(env_util, "base_env_dir", return_value=base):
            self.assertEqual(env_util.resolve_task_python(task),
                             str(base / "bin" / "python"))


if __name__ == "__main__":
    unittest.main()
