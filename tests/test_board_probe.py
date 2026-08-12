"""板端环境探测输出解析测试（纯函数，不需要真实板子）。"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.board_util import (  # noqa: E402
    parse_board_probe,
    suggest_ld_library_path,
)


class BoardProbeTest(unittest.TestCase):
    def test_parse_full_probe(self):
        out = """\
## chip
AX650A
## ax_run_model
/opt/bin/ax_run_model
## python
Python 3.8.10
## pyaxengine
ok 0.1.3
## libax_engine
libax_engine.so (libc6) => /usr/local/lib/libax_engine.so
/soc/lib/libax_engine.so
## ld_path
/usr/local/lib
"""
        env = parse_board_probe(out)
        self.assertEqual(env["chip_type"], "AX650A")
        self.assertEqual(env["ax_run_model"], "/opt/bin/ax_run_model")
        self.assertEqual(env["python_version"], "Python 3.8.10")
        self.assertEqual(env["pyaxengine"], "0.1.3")
        self.assertIn("/usr/local/lib/libax_engine.so", env["libax_engine"])
        self.assertIn("/soc/lib/libax_engine.so", env["libax_engine"])
        self.assertEqual(env["ld_library_path"], "/usr/local/lib")

    def test_parse_missing_pyaxengine(self):
        out = """\
## chip
AX650
## ax_run_model
/opt/bin/ax_run_model
## python
Python 3.8.10
## pyaxengine
ModuleNotFoundError: No module named 'axengine'
## libax_engine
## ld_path

"""
        env = parse_board_probe(out)
        self.assertIsNone(env["pyaxengine"])
        self.assertIn("No module named", env["pyaxengine_error"])

    def test_suggest_ld_library_path(self):
        env = {
            "libax_engine": ["/usr/local/lib/libax_engine.so"],
            "ld_library_path": "/opt/lib",
        }
        path = suggest_ld_library_path(env)
        self.assertTrue(path.startswith("/usr/local/lib"))
        self.assertIn("/soc/lib", path)
        self.assertIn("/opt/lib", path)
        # 探测到的目录优先、无重复
        self.assertEqual(path.count("/usr/local/lib"), 1)


if __name__ == "__main__":
    unittest.main()
