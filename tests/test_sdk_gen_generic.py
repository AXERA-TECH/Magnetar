"""通用 SDK 生成（sdk_gen.run_generic_python/cpp）单元测试。

覆盖：基于 model_meta + model_flow 生成 Python SDK 并用 onnxruntime 跑通真实样本、
model_flow 一致性校验（缺失/路径错误/语法错误）、C++ SDK CMake configure。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.export_onnx import export_to_onnx  # noqa: E402
from magnetar.stages.sdk_gen import (  # noqa: E402
    make_npu_only_sdk_dir,
    run_generic_cpp,
    run_generic_python,
)


class TinyCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(nn.Conv2d(3, 8, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2))
        self.head = nn.Linear(8 * 8 * 8, 10)

    def forward(self, x):
        x = self.features(x)
        return self.head(x.flatten(1))


def make_task_dir(tmp: Path) -> Path:
    task_dir = tmp / "task"
    export_to_onnx(
        task_dir,
        model=TinyCNN().eval(),
        example_inputs=torch.randn(1, 3, 16, 16),
        model_name="tiny_cnn",
    )
    flow = {
        "model_name": "tiny_cnn",
        "framework": "pytorch",
        "source": "local test model",
        "example_input": "export/sample_input.npy",
        "preprocess_code": (
            "import numpy as np\n"
            "def preprocess(*arrays):\n"
            "    return [np.ascontiguousarray(a, dtype=np.float32) for a in arrays]\n"
        ),
        "postprocess_code": (
            "import numpy as np\n"
            "def postprocess(*arrays):\n"
            "    return {'top1': int(np.argmax(arrays[0]))}\n"
        ),
        "preprocess_note": "float32 直通",
        "postprocess_note": "argmax top1",
        "verified": True,
    }
    (task_dir / "origin").mkdir(exist_ok=True)
    (task_dir / "origin" / "model_flow.json").write_text(
        json.dumps(flow, ensure_ascii=False), encoding="utf-8")
    return task_dir


class SdkGenGenericTest(unittest.TestCase):
    def test_generic_python_sdk_runs_with_onnxruntime(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = make_task_dir(Path(tmp))
            ps = run_generic_python(task_dir, model_name="tiny_cnn")
            for name in ("__init__.py", "inference.py", "preprocess.py", "postprocess.py",
                         "example.py", "requirements.txt", "README.md"):
                self.assertTrue((ps / name).is_file(), name)

            # SDK 默认 AxEngineExecutionProvider 不可用时应回退 onnxruntime CPU
            out_dir = Path(tmp) / "py_out"
            proc = subprocess.run(
                [
                    sys.executable, str(ps / "example.py"),
                    "--model", str(task_dir / "export" / "model.onnx"),
                    "--input", str(task_dir / "export" / "sample_input.npy"),
                    "--output-dir", str(out_dir),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            sdk_out = np.load(out_dir / "output_0.npy").astype(np.float32)

            sess = ort.InferenceSession(
                str(task_dir / "export" / "model.onnx"), providers=["CPUExecutionProvider"])
            sample = np.load(task_dir / "export" / "sample_input.npy").astype(np.float32)
            ref = sess.run(None, {"input_0": sample})[0].astype(np.float32)
            cos = float(np.dot(sdk_out.ravel(), ref.ravel()) /
                        (np.linalg.norm(sdk_out) * np.linalg.norm(ref) + 1e-12))
            self.assertGreaterEqual(cos, 0.9999)

    def test_flow_missing_generates_identity_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "task"
            export_to_onnx(
                task_dir,
                model=TinyCNN().eval(),
                example_inputs=torch.randn(1, 3, 16, 16),
                model_name="tiny_cnn",
            )
            ps = run_generic_python(task_dir, model_name="tiny_cnn")
            self.assertIn("float32", (ps / "preprocess.py").read_text(encoding="utf-8"))

    def test_flow_example_input_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "task"
            export_to_onnx(
                task_dir,
                model=TinyCNN().eval(),
                example_inputs=torch.randn(1, 3, 16, 16),
                model_name="tiny_cnn",
            )
            (task_dir / "origin").mkdir(exist_ok=True)
            (task_dir / "origin" / "model_flow.json").write_text(
                json.dumps({"example_input": "export/not_exists.npy"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_generic_python(task_dir, model_name="tiny_cnn")

    def test_flow_preprocess_syntax_error_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "task"
            export_to_onnx(
                task_dir,
                model=TinyCNN().eval(),
                example_inputs=torch.randn(1, 3, 16, 16),
                model_name="tiny_cnn",
            )
            (task_dir / "origin").mkdir(exist_ok=True)
            (task_dir / "origin" / "model_flow.json").write_text(
                json.dumps({"preprocess_code": "def broken(:\n"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_generic_python(task_dir, model_name="tiny_cnn")

    def test_generic_cpp_sdk_cmake_configure(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = make_task_dir(Path(tmp))
            cpp = run_generic_cpp(task_dir, model_name="tiny_cnn", target_hw="AX650")
            for name in ("CMakeLists.txt", "include/model_runner.hpp",
                         "src/model_runner.cpp", "examples/main.cpp", "README.md"):
                self.assertTrue((cpp / name).is_file(), name)
            build_dir = Path(tmp) / "cpp_build"
            proc = subprocess.run(
                ["cmake", "-S", str(cpp), "-B", str(build_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_strict_npu_sdk_has_no_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = make_task_dir(Path(tmp))
            ps = run_generic_python(task_dir, model_name="tiny_cnn", strict_npu=True)
            inference = (ps / "inference.py").read_text(encoding="utf-8")
            self.assertNotIn("import onnxruntime", inference)
            self.assertNotIn("ort.InferenceSession", inference)
            self.assertIn("axengine", inference)
            readme = (ps / "README.md").read_text(encoding="utf-8")
            self.assertIn("NPU 专用", readme)

    def test_make_npu_only_sdk_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = make_task_dir(Path(tmp))
            ps = run_generic_python(task_dir, model_name="tiny_cnn")  # 开发版
            self.assertIn("import onnxruntime", (ps / "inference.py").read_text(encoding="utf-8"))

            changed = make_npu_only_sdk_dir(ps.parent)
            self.assertTrue(changed)
            self.assertNotIn(
                "import onnxruntime", (ps / "inference.py").read_text(encoding="utf-8"))
            # 幂等：再次调用不再替换
            self.assertFalse(make_npu_only_sdk_dir(ps.parent))

    def test_assemble_strips_fallback_only_after_runonboard(self):
        from magnetar.stages.package import assemble

        def build_package(root: Path, npu_verified: bool) -> Path:
            task_dir = make_task_dir(root)
            compile_dir = task_dir / "compile"
            compile_dir.mkdir(exist_ok=True)
            (compile_dir / "model.axmodel").write_bytes(b"x" * 2048)
            if npu_verified:
                rb = task_dir / "runonboard"
                rb.mkdir(exist_ok=True)
                (rb / "runonboard_report.md").write_text(
                    "# Run On Board Report\n\n- python_cpp_cosine: 0.999\n",
                    encoding="utf-8",
                )
            run_generic_python(task_dir, model_name="tiny_cnn")
            return assemble(task_dir, metrics={"cosine_similarity": 0.99},
                            pulsar_image="pulsar2:7.0", model_name="tiny_cnn")

        with tempfile.TemporaryDirectory() as tmp:
            # 有 runonboard 报告 → 发布包 SDK 去掉 onnxruntime
            pkg = build_package(Path(tmp) / "a", True)
            inference = (pkg / "python" / "tiny_cnn_sdk" / "inference.py").read_text(encoding="utf-8")
            self.assertNotIn("import onnxruntime", inference)
            self.assertTrue((pkg / "NPU_ONLY_SDK.md").is_file())

            # 无 runonboard 报告 → 保留开发版 fallback
            pkg2 = build_package(Path(tmp) / "b", False)
            inference2 = (pkg2 / "python" / "tiny_cnn_sdk" / "inference.py").read_text(encoding="utf-8")
            self.assertIn("import onnxruntime", inference2)
            self.assertFalse((pkg2 / "NPU_ONLY_SDK.md").exists())


if __name__ == "__main__":
    unittest.main()
