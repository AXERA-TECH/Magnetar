"""C++ SDK 模板回归测试：API 调用/链接库/初始化写法与 BSP 3.10.2 兼容。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.stages import sdk_gen  # noqa: E402


class CppSdkTemplateTest(unittest.TestCase):
    def setUp(self):
        self.task = Path(tempfile.mkdtemp(prefix="cpp_sdk_template_"))
        origin = self.task / "origin"
        origin.mkdir()
        (origin / "model_flow.json").write_text(json.dumps({
            "model_name": "demo", "framework": "onnx", "source": "local",
            "verified": True,
        }, indent=2), encoding="utf-8")
        (self.task / "export").mkdir()
        (self.task / "export" / "model_meta.json").write_text(json.dumps({
            "model_name": "demo",
            "inputs": [{"name": "input", "shape": [1, 3, 4], "dtype": "float32"}],
            "outputs": [{"name": "output", "shape": [1, 4], "dtype": "float32"}],
        }, indent=2), encoding="utf-8")
        sdk_gen.run_generic_cpp(self.task)

    def _read(self, rel):
        return (self.task / "sdk" / "cpp" / rel).read_text(encoding="utf-8")

    def test_runner_uses_run_sync_v2(self):
        src = self._read("src/model_runner.cpp")
        self.assertIn("AX_ENGINE_RunSyncV2(impl_->handle, impl_->context", src)
        self.assertNotIn("AX_ENGINE_Run(", src)

    def test_example_avoids_most_vexing_parse(self):
        main = self._read("examples/main.cpp")
        self.assertIn("std::vector<char> bytes{", main)

    def test_cmake_links_interpreter_and_runtime_root(self):
        cmake = self._read("CMakeLists.txt")
        for lib in ("ax_engine", "ax_interpreter", "ax_sys"):
            self.assertIn(lib, cmake, f"CMake 应链接 {lib}")
        self.assertIn("${AX_RUNTIME_ROOT}/lib", cmake)


if __name__ == "__main__":
    unittest.main()
