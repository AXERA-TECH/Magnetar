"""BSP 公共目录管理测试（mock 下载/解压，不做真实下载）。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import magnetar.bsp_util as bsp_util  # noqa: E402


class BspUtilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="magnetar_bsp_test_"))

    def _fake_runtime(self, base: Path) -> Path:
        (base / "include").mkdir(parents=True)
        (base / "lib").mkdir()
        (base / "include" / "ax_engine_api.h").touch()
        (base / "lib" / "libax_engine.so").touch()
        return base

    def test_bsp_root_env_override(self):
        with mock.patch.dict(os.environ, {"MAGNETAR_BSP_HOME": str(self.tmp / "bsp")}):
            self.assertEqual(bsp_util.bsp_root(), self.tmp / "bsp")

    def test_find_runtime_root(self):
        rt = self._fake_runtime(self.tmp / "sdk")
        self.assertEqual(bsp_util.find_runtime_root(self.tmp), rt)
        self.assertIsNone(bsp_util.find_runtime_root(self.tmp / "missing"))

    def test_find_cross_compiler_priority(self):
        bsp = self.tmp / "bsp"
        (bsp / "toolchain" / "bin").mkdir(parents=True)
        gcc = bsp / "toolchain" / "bin" / "aarch64-none-linux-gnu-g++"
        gcc.touch()
        with mock.patch.dict(os.environ, {"AARCH64_GXX": str(gcc)}):
            self.assertEqual(bsp_util.find_cross_compiler(bsp), gcc)
        os.environ.pop("AARCH64_GXX", None)
        self.assertEqual(bsp_util.find_cross_compiler(bsp), gcc)

    def test_cache_roundtrip(self):
        home = self.tmp / "ax650"
        home.mkdir(parents=True)
        rt = self.tmp / "rt"
        rt.mkdir()
        info = {"bsp_dir": str(home), "runtime_root": str(rt), "cross_compiler": None}
        bsp_util._save_cache(home, info)
        self.assertEqual(bsp_util._load_cache(home), info)

    def test_ensure_ax650_uses_cache(self):
        home = self.tmp / "ax650"
        rt = self._fake_runtime(home / "sdk")
        bsp_util._save_cache(home, {"bsp_dir": str(home), "runtime_root": str(rt)})
        with mock.patch.object(bsp_util, "_download") as dl:
            info = bsp_util._ensure_ax650(home, None, force=False)
        dl.assert_not_called()
        self.assertEqual(info["runtime_root"], str(rt))

    def test_ensure_ax650_downloads_and_extracts(self):
        home = self.tmp / "ax650"
        home.mkdir(parents=True)
        rt = self._fake_runtime(home / "extracted" / "sdk")
        with mock.patch.object(bsp_util, "_download") as dl, \
             mock.patch.object(bsp_util, "_run") as run, \
             mock.patch.object(bsp_util, "_ensure_toolchain") as tc, \
             mock.patch.object(bsp_util, "find_runtime_root",
                               return_value=rt) as fr:
            info = bsp_util._ensure_ax650(home, None, force=False)
        dl.assert_called_once()
        tc.assert_called_once()
        self.assertTrue(str(dl.call_args.args[0]).startswith("https://"))
        self.assertTrue(any("tar" in c.args[0] for c in run.call_args_list))
        self.assertEqual(info["runtime_root"], str(rt))
        self.assertEqual(
            json.loads((home / "bsp_info.json").read_text(encoding="utf-8"))["runtime_root"],
            str(rt),
        )

    def test_ensure_bsp_dispatch(self):
        with mock.patch.object(bsp_util, "_ensure_ax650", return_value={"ok": 1}) as a650, \
             mock.patch.object(bsp_util, "_ensure_ax620e", return_value=None) as a620:
            bsp_util.ensure_bsp("AX650", None)
            bsp_util.ensure_bsp("AX620E", None)
            bsp_util.ensure_bsp("weird", None)
        a650.assert_called_once()
        a620.assert_called_once()

    def test_build_cpp_sdk(self):
        task = self.tmp / "task"
        (task / "sdk" / "cpp").mkdir(parents=True)
        (task / "sdk" / "cpp" / "CMakeLists.txt").touch()
        bsp = {"runtime_root": "/rt", "cross_compiler": "/gcc"}
        with mock.patch.object(bsp_util, "ensure_bsp", return_value=bsp), \
             mock.patch.object(bsp_util, "_run") as run:
            exe = bsp_util.build_cpp_sdk(task)
        self.assertIsNone(exe)  # 未真正产出可执行文件
        cmds = [c.args[0] for c in run.call_args_list]
        self.assertTrue(any("-DAX_RUNTIME_ROOT=/rt" in c for c in cmds))
        self.assertTrue(any("-DCMAKE_CXX_COMPILER=/gcc" in c for c in cmds))

    def test_build_cpp_sdk_degrades_without_bsp(self):
        task = self.tmp / "task"
        with mock.patch.object(bsp_util, "ensure_bsp", return_value=None), \
             mock.patch.object(bsp_util, "_run") as run:
            self.assertIsNone(bsp_util.build_cpp_sdk(task))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
