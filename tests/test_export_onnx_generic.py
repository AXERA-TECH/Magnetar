"""通用 ONNX 导出器（magnetar/export_onnx.py）单元测试。

覆盖：简单模型导出成功路径、多输入多输出、load 脚本入口、
动态 shape 检测、缺参报错、CLI 冒烟。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnx
import torch
import torch.nn as nn
from onnx import TensorProto, helper

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.export_onnx import ExportError, _check_static, export_to_onnx  # noqa: E402


class TinyCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(nn.Conv2d(3, 8, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2))
        self.head = nn.Linear(8 * 8 * 8, 10)

    def forward(self, x):
        x = self.features(x)
        return self.head(x.flatten(1))


class MultiIO(nn.Module):
    def forward(self, a, b):
        return a + b, a - b


class ExportOnnxGenericTest(unittest.TestCase):
    def test_simple_model_export_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            result = export_to_onnx(
                task_dir,
                model=TinyCNN().eval(),
                example_inputs=torch.randn(1, 3, 16, 16),
                model_name="tiny_cnn",
            )
            self.assertGreaterEqual(result["cosine"], 0.99)
            export_dir = task_dir / "export"
            self.assertTrue((export_dir / "model.onnx").is_file())
            self.assertTrue((export_dir / "model_meta.json").is_file())
            self.assertTrue((export_dir / "export_report.md").is_file())
            self.assertTrue((export_dir / "sample_input.npy").is_file())
            self.assertTrue((export_dir / "source_output.npy").is_file())

            meta = json.loads((export_dir / "model_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["model_name"], "tiny_cnn")
            self.assertEqual(meta["inputs"][0]["shape"], [1, 3, 16, 16])
            self.assertEqual(meta["outputs"][0]["shape"], [1, 10])
            self.assertEqual(meta["opset"], 17)
            self.assertIn("export_attempts", meta)

            calib_dir = export_dir / "calib_data" / "input_0"
            self.assertEqual(len(list(calib_dir.glob("*.npy"))), 4)
            self.assertTrue((export_dir / "calib_data" / "input_0.tar.gz").is_file())

    def test_multi_io_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            result = export_to_onnx(
                task_dir,
                model=MultiIO().eval(),
                example_inputs=(torch.randn(2, 4), torch.randn(2, 4)),
                input_names=["left", "right"],
                model_name="multi",
            )
            self.assertGreaterEqual(result["cosine"], 0.99)
            self.assertEqual(result["input_names"], ["left", "right"])
            meta = result["model_meta"]
            self.assertEqual([i["name"] for i in meta["inputs"]], ["left", "right"])
            self.assertEqual(len(meta["outputs"]), 2)
            for name in ["left", "right"]:
                self.assertTrue((task_dir / "export" / "calib_data" / name).is_dir())

    def test_load_script_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "load.py"
            script.write_text(
                "import torch\n"
                "import torch.nn as nn\n"
                "class Loaded(nn.Module):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.l = nn.Linear(8, 4)\n"
                "    def forward(self, x):\n"
                "        return self.l(x)\n"
                "def build():\n"
                "    return Loaded().eval(), (torch.randn(1, 8),)\n",
                encoding="utf-8",
            )
            task_dir = root / "task"
            result = export_to_onnx(task_dir, load_script=script, model_name="scripted")
            self.assertGreaterEqual(result["cosine"], 0.99)
            self.assertTrue((task_dir / "export" / "model.onnx").is_file())

    def test_dynamic_shape_detected(self):
        nodes = [helper.make_node("Relu", ["x"], ["y"])]
        graph = helper.make_graph(
            nodes,
            "dyn",
            [helper.make_tensor_value_info("x", TensorProto.FLOAT, ["N", 4])],
            [helper.make_tensor_value_info("y", TensorProto.FLOAT, [None, 4])],
        )
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dyn.onnx"
            onnx.save(model, str(path))
            is_static, dims = _check_static(path)
            self.assertFalse(is_static)
            self.assertTrue(any(d["kind"] == "input" and d["name"] == "x" for d in dims))

    def test_missing_model_source_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                export_to_onnx(Path(tmp), example_inputs=torch.randn(1, 3))

    def test_export_error_carries_attempts(self):
        class Broken(nn.Module):
            def forward(self, x):
                return x.item()  # 不可 trace

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ExportError) as ctx:
                export_to_onnx(Path(tmp), model=Broken().eval(), example_inputs=torch.randn(1))
            self.assertTrue(ctx.exception.attempts)
            self.assertTrue((Path(tmp) / "export" / "export_report.md").is_file())

    def test_cli_help(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "export_onnx.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--load-script", proc.stdout)
        self.assertIn("--input-shapes", proc.stdout)


if __name__ == "__main__":
    unittest.main()
