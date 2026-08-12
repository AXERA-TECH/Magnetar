"""pulsar2_ref：cheatsheet 单一来源 + 业务规则校验测试。"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.pulsar2_ref import render_cheatsheet_markdown, validate_config  # noqa: E402

ENUMS = {
    "ModelType": {"ONNX": 0, "QuantAxModel": 1},
    "DataFormat": {"Image": 0, "Numpy": 1, "Binary": 2, "NumpyObject": 3},
    "QuantMethod": {"MinMax": 0, "Percentile": 1, "MSE": 2, "KL": 3},
    "DataType": {"U8": 1, "S8": 2, "U16": 3, "S16": 4, "FP16": 9, "FP32": 10},
}


class Pulsar2RefTest(unittest.TestCase):
    def test_cheatsheet_matches_generated_doc(self):
        doc = REPO_ROOT / "docs" / "input-format-cheatsheet.md"
        self.assertTrue(doc.is_file(), "cheatsheet 文档缺失")
        self.assertEqual(
            doc.read_text(encoding="utf-8"),
            render_cheatsheet_markdown(),
            "docs/input-format-cheatsheet.md 与代码不一致，"
            "请执行 python magnetar/pulsar2_ref.py --write-cheatsheet",
        )

    def test_validate_config_business_rules(self):
        cfg = {
            "input_shapes": "input:1x3x224x224",
            "model_type": "ONNX",
            "quant": {
                "calibration_method": "MinMax",
                "input_configs": [{
                    "tensor_name": "input",
                    "calibration_format": "Numpy",
                    "calibration_size": 8,
                }],
            },
            "input_processors": [{
                "tensor_name": "input",
                "src_dtype": "U8",
                "src_layout": "NHWC",
            }],
        }
        warnings = validate_config(cfg, ENUMS)
        self.assertTrue(
            any("U8 输入" in w for w in warnings),
            "U8 输入缺 calibration_std=255 应产生警告",
        )

        cfg2 = dict(cfg)
        cfg2["quant"] = {
            "input_configs": [{
                "tensor_name": "input",
                "calibration_format": "Numpy",
                "calibration_size": 8,
                "calibration_std": [255, 255, 255],
            }],
            "calibration_method": "MinMax",
            "enable_smooth_quant": True,
            "enable_brecq": True,
        }
        warnings2 = validate_config(cfg2, ENUMS)
        self.assertTrue(any("三选一" in w for w in warnings2))


if __name__ == "__main__":
    unittest.main()
