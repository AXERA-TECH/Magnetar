"""proto_schema 字段级校验测试（本地 proto 缓存，不依赖 docker）。"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.proto_schema import (  # noqa: E402
    parse_input_shapes_str,
    parse_proto_files,
)

CACHE = REPO_ROOT / "cache" / "pulsar2" / "pulsar2_7.0"


def _schema():
    return parse_proto_files([CACHE / "common.proto", CACHE / "build_config.proto"])


def _good_config():
    return {
        "input": "/workspace/export/model.onnx",
        "output_dir": "/workspace/compile",
        "output_name": "model.axmodel",
        "model_type": "ONNX",
        "target_hardware": "AX650",
        "npu_mode": "NPU1",
        "input_shapes": "input:1x3x224x224",
        "onnx_opt": {"disable_onnx_optimization": False, "model_check": True},
        "quant": {
            "input_configs": [{
                "tensor_name": "input",
                "calibration_dataset": "/workspace/export/calib_data/input.tar.gz",
                "calibration_format": "Numpy",
                "calibration_size": 8,
            }],
            "calibration_method": "MinMax",
            "highest_mix_precision": False,
        },
        "input_processors": [{
            "tensor_name": "input",
            "tensor_layout": "NCHW",
            "src_dtype": "FP32",
            "src_layout": "NCHW",
        }],
    }


@unittest.skipUnless(CACHE.is_dir(), "proto 缓存不存在")
class ProtoSchemaTest(unittest.TestCase):
    def test_good_config_passes(self):
        self.assertEqual(_schema().validate(_good_config()), [])

    def test_unknown_field_detected(self):
        cfg = _good_config()
        cfg["unknown_opt"] = 1
        errors = _schema().validate(cfg)
        self.assertTrue(any("未知字段" in e and "unknown_opt" in e for e in errors))

    def test_enum_membership_and_type(self):
        cfg = _good_config()
        cfg["npu_mode"] = "NPU9"
        cfg["input"] = 123
        errors = _schema().validate(cfg)
        self.assertTrue(any("NPU9" in e for e in errors))
        self.assertTrue(any("期望字符串" in e for e in errors))

    def test_required_field_missing(self):
        cfg = _good_config()
        del cfg["output_dir"]
        errors = _schema().validate(cfg)
        self.assertTrue(any("必填字段缺失" in e and "output_dir" in e for e in errors))

    def test_repeated_field_type(self):
        cfg = _good_config()
        cfg["input_processors"] = {"tensor_name": "input"}
        errors = _schema().validate(cfg)
        self.assertTrue(any("期望数组" in e for e in errors))

    def test_parse_input_shapes(self):
        self.assertEqual(
            parse_input_shapes_str("input:1x3x224x224;mask:1x512"),
            {"input": [1, 3, 224, 224], "mask": [1, 512]},
        )
        self.assertEqual(parse_input_shapes_str(""), {})


if __name__ == "__main__":
    unittest.main()
