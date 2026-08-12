"""Pulsar2 后端（独立包/docker）解析与执行测试。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.docker_util import (  # noqa: E402
    extract_pulsar2_proto,
    find_pulsar2_home,
    parse_backend,
    resolve_backend,
    run_pulsar2,
)


def _fake_package_home() -> Path:
    """构造一个最小独立包：main.py 存根 + install license + proto。"""
    home = Path(tempfile.mkdtemp(prefix="pulsar2_pkg_test_"))
    (home / "bin").mkdir()
    (home / "bin" / "pulsar2").write_text("#!/bin/bash\necho stub\n", encoding="utf-8")
    (home / "bin" / "pulsar2").chmod(0o755)
    main = home / "pulsar2" / "axnn" / "yamain"
    main.mkdir(parents=True)
    (main / "main.py").write_text(
        "import os, sys\n"
        "print('MAIN', sys.argv[1:])\n"
        "print('FLOAT=' + os.environ.get('FLOAT_MATMUL_USE_CONV_EU', ''))\n"
        "print('WS_IN_PYTHONPATH', 'pulsar2' in os.environ.get('PYTHONPATH', ''))\n",
        encoding="utf-8",
    )
    (home / "install").mkdir()
    (home / "install" / "Unlocked_20230901_perpetual.v2c").write_bytes(b"fake-license")
    cfg = home / "pulsar2" / "axnn" / "yamain" / "config"
    cfg.mkdir(parents=True)
    (cfg / "common.proto").write_text('enum DataType { U8 = 1; FP32 = 10; }\n', encoding="utf-8")
    (cfg / "build_config.proto").write_text(
        'enum ModelType { ONNX = 0; }\nmessage BuildConfig { string input = 1; }\n',
        encoding="utf-8",
    )
    return home


class Pulsar2BackendTest(unittest.TestCase):
    def setUp(self):
        self.home = _fake_package_home()
        self._old_home = os.environ.get("PULSAR2_HOME")
        os.environ["PULSAR2_HOME"] = str(self.home)

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("PULSAR2_HOME", None)
        else:
            os.environ["PULSAR2_HOME"] = self._old_home

    def test_find_and_resolve_package(self):
        self.assertEqual(find_pulsar2_home(), self.home)
        handle = resolve_backend()
        self.assertTrue(handle.startswith("pkg:"))
        kind, name = parse_backend(handle)
        self.assertEqual((kind, Path(name)), ("package", self.home))

    def test_parse_backend_compat(self):
        self.assertEqual(parse_backend("pkg:/x"), ("package", "/x"))
        self.assertEqual(parse_backend("img:pulsar2:7.0"), ("docker", "pulsar2:7.0"))
        self.assertEqual(parse_backend("pulsar2:7.0"), ("docker", "pulsar2:7.0"))

    def test_run_pulsar2_package_mode(self):
        out = run_pulsar2(
            f"pkg:{self.home}",
            str(self.home),
            "FLOAT_MATMUL_USE_CONV_EU=1 pulsar2 build --config x.json",
            timeout=60,
        )
        self.assertIn("MAIN ['build', '--config', 'x.json']", out)
        self.assertIn("FLOAT=1", out)
        self.assertIn("WS_IN_PYTHONPATH True", out)
        # license 自动安装
        self.assertTrue(
            (Path.home() / ".hasplm" / "installed" / "32434" / "Unlocked_20230901_perpetual.v2c").is_file()
        )

    def test_run_pulsar2_package_missing_main(self):
        empty = Path(tempfile.mkdtemp())
        with self.assertRaises(RuntimeError):
            run_pulsar2(f"pkg:{empty}", str(empty), "pulsar2 version", timeout=60)

    def test_extract_proto_package(self):
        files = extract_pulsar2_proto(f"pkg:{self.home}", force=True)
        self.assertTrue(files["common.proto"].is_file())
        self.assertTrue(files["build_config.proto"].is_file())
        self.assertIn("DataType", files["common.proto"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
