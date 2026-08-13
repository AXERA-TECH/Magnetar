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
        entry = {
            "msp_zip_name": "msp_50_3.10.2.zip",
            "msp_url": "https://example.com/msp_50_3.10.2.zip",
            "toolchain_url": "https://example.com/gcc-arm.tar.xz",
            "compiler_check": "aarch64-none-linux-gnu-g++",
        }
        with mock.patch.object(bsp_util, "_chip_entry", return_value=entry) as ce, \
             mock.patch.object(bsp_util, "_download") as dl, \
             mock.patch.object(bsp_util, "_extract_bsp_archive",
                               return_value=rt) as ex, \
             mock.patch.object(bsp_util, "_ensure_toolchain") as tc, \
             mock.patch.object(bsp_util, "find_cross_compiler",
                               return_value=Path("/gcc")):
            info = bsp_util._ensure_ax650(home, None, force=False)
        ce.assert_called_once()
        dl.assert_called_once()
        self.assertEqual(dl.call_args.args[0], entry["msp_url"])
        self.assertEqual(dl.call_args.args[1], home / entry["msp_zip_name"])
        ex.assert_called_once()
        tc.assert_called_once()
        self.assertEqual(info["runtime_root"], str(rt))
        self.assertEqual(info["version"], "V3.10.2")
        self.assertEqual(
            json.loads((home / "bsp_info.json").read_text(encoding="utf-8"))["runtime_root"],
            str(rt),
        )

    def test_parse_build_common(self):
        text = '''case "${CHIP}" in
  ax650)
    MSP_ZIP_NAME="msp_50_3.10.2.zip"
    MSP_URL_DEFAULT="https://example.com/msp_50_3.10.2.zip"
    MSP_EXTRACT_DIR="${ROOT_DIR}/.ci/msp/ax650"
    TOOLCHAIN_ARCHIVE_NAME="gcc-arm-9.2-2019.12-x86_64-aarch64-none-linux-gnu.tar.xz"
    TOOLCHAIN_URL_DEFAULT="https://example.com/${TOOLCHAIN_ARCHIVE_NAME}"
    COMPILER_CHECK="aarch64-none-linux-gnu-g++"
    ;;
  *)
    echo "unsupported"
    ;;
esac
'''
        entries = bsp_util._parse_build_common(text)
        self.assertEqual(entries["ax650"]["MSP_ZIP_NAME"], "msp_50_3.10.2.zip")
        self.assertEqual(entries["ax650"]["MSP_URL_DEFAULT"],
                         "https://example.com/msp_50_3.10.2.zip")
        self.assertNotIn("axcl", entries)

    def test_chip_entry_expands_toolchain_var(self):
        text = '''case "${CHIP}" in
  ax650)
    MSP_ZIP_NAME="msp_50_3.10.2.zip"
    MSP_URL_DEFAULT="https://example.com/msp.zip"
    TOOLCHAIN_ARCHIVE_NAME="gcc-arm.tar.xz"
    TOOLCHAIN_URL_DEFAULT="https://example.com/${TOOLCHAIN_ARCHIVE_NAME}"
    COMPILER_CHECK="aarch64-none-linux-gnu-g++"
    ;;
esac
'''
        with mock.patch.object(bsp_util, "_fetch_build_common",
                               return_value=text):
            entry = bsp_util._chip_entry("AX650", None)
        self.assertEqual(entry["msp_zip_name"], "msp_50_3.10.2.zip")
        self.assertEqual(entry["toolchain_url"], "https://example.com/gcc-arm.tar.xz")
        with self.assertRaises(RuntimeError):
            bsp_util._chip_entry("AX999", None)

    def test_extract_msp_zip(self):
        home = self.tmp / "ax650"
        home.mkdir(parents=True)
        zpath = home / "msp_50_3.10.2.zip"
        import zipfile
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("msp/out/include/ax_engine_api.h", "x")
            z.writestr("msp/out/lib/libax_engine.so", "x")
        rt = bsp_util._extract_bsp_archive(home, zpath)
        self.assertEqual(rt, home / "msp" / "out")
        self.assertTrue((rt / "include" / "ax_engine_api.h").is_file())

    def test_ensure_bsp_dispatch(self):
        with mock.patch.object(bsp_util, "_ensure_ax650", return_value={"ok": 1}) as a650, \
             mock.patch.object(bsp_util, "_ensure_chip",
                               return_value={"ok": 2}) as chip:
            bsp_util.ensure_bsp("AX650", None)
            bsp_util.ensure_bsp("AX630C", None)
            bsp_util.ensure_bsp("AX620E", None)
            bsp_util.ensure_bsp("AX620Q", None)
            bsp_util.ensure_bsp("weird", None)
        a650.assert_called_once()
        self.assertEqual(chip.call_count, 3)
        self.assertEqual(chip.call_args_list[0].args[1], "ax630c")
        self.assertEqual(chip.call_args_list[1].args[1], "ax620q")

    def test_ensure_chip_downloads_runtime_and_toolchain(self):
        home = self.tmp / "ax630c"
        home.mkdir(parents=True)
        rt = self._fake_runtime(home / "extracted" / "sdk")
        entry = {
            "msp_zip_name": "msp_20e_3.0.0.zip",
            "msp_url": "https://example.com/msp_20e_3.0.0.zip",
            "toolchain_url": "https://example.com/gcc.tar.xz",
            "compiler_check": "aarch64-none-linux-gnu-g++",
        }
        with mock.patch.object(bsp_util, "_chip_entry", return_value=entry) as ce, \
             mock.patch.object(bsp_util, "_download") as dl, \
             mock.patch.object(bsp_util, "_extract_bsp_archive",
                               return_value=rt) as ex, \
             mock.patch.object(bsp_util, "_ensure_toolchain") as tc, \
             mock.patch.object(bsp_util, "find_cross_compiler",
                               return_value=Path("/gcc")):
            info = bsp_util._ensure_chip(home, "ax630c", None, force=False)
        ce.assert_called_once_with("ax630c", None)
        dl.assert_called_once()
        self.assertEqual(dl.call_args.args[0], entry["msp_url"])
        self.assertEqual(dl.call_args.args[1], home / entry["msp_zip_name"])
        ex.assert_called_once()
        tc.assert_called_once_with(home, None, entry)
        self.assertEqual(info["runtime_root"], str(rt))
        self.assertEqual(info["version"], "V3.0.0")

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
