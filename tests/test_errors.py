"""类型化错误码注册表与异常分类的单元测试。"""
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.errors import (  # noqa: E402
    ALL_CODES,
    BLOCK_CODES,
    ERROR_CODES,
    MagnetarError,
    classify_error,
)
from magnetar.export_onnx import ExportError, ExportAttempt  # noqa: E402


class ErrorsTest(unittest.TestCase):
    def test_yaml_retry_on_codes_are_registered(self):
        """magnetar.yaml 每个步骤的 retry_on 都必须已登记为可重试错误码。"""
        yaml_path = REPO_ROOT / "workflows" / "magnetar.yaml"
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        retry_on = {
            code
            for step in data["workflow"]["steps"]
            for code in step.get("retry", {}).get("retry_on", [])
        }
        self.assertGreater(len(retry_on), 0)
        self.assertEqual(retry_on - set(ERROR_CODES), set(),
                         "yaml retry_on 存在未登记错误码，请同步 magnetar.errors.ERROR_CODES")
        # 可重试码不得混入 STOP/阻塞码区
        self.assertEqual(retry_on & set(BLOCK_CODES), set())

    def test_magnetar_error_rejects_unknown_code(self):
        with self.assertRaises(ValueError):
            MagnetarError("typo_code", "boom")

    def test_magnetar_error_carries_code_and_fatal(self):
        err = MagnetarError("compile_failed", "build broke", fatal=False)
        self.assertEqual(err.code, "compile_failed")
        self.assertFalse(err.fatal)
        self.assertIn("compile_failed", str(err))

    def test_classify_error_walks_cause_chain(self):
        try:
            try:
                raise MagnetarError("network_timeout", "timeout")
            except MagnetarError as e:
                raise ValueError("outer wrapper") from e
        except ValueError as outer:
            self.assertEqual(classify_error(outer), "network_timeout")
            self.assertIsNone(classify_error(ValueError("plain")))

    def test_export_error_classifies_as_export_failed(self):
        err = ExportError("all export paths failed", attempts=[])
        self.assertIsInstance(err, MagnetarError)
        self.assertEqual(classify_error(err), "export_failed")
        self.assertIn("export_failed", ALL_CODES)


if __name__ == "__main__":
    unittest.main()
