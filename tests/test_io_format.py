"""AX 输入/输出格式单一来源测试（固化成功案例格式）。

锁定 docs/input-format-cheatsheet.md 中验证过的格式：
- pulsar2 run：输入 `{tensor名}.bin`（float32 raw），输出 `{输出名}.bin`
- ax_run_model：`{tensor名}.bin` + input_list.txt，输出目录第一个 *.bin
- 校准数据：tar.gz 内含 npy，可完整回读
"""
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from magnetar.io_format import (  # noqa: E402
    pack_calibration_npy,
    read_ax_run_model_output,
    read_pulsar2_run_output,
    read_raw_float32,
    write_ax_run_model_input,
    write_pulsar2_run_input,
    write_raw_float32,
)


class IOFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pulsar2_run_roundtrip(self):
        arr = np.arange(24, dtype=np.float32).reshape(1, 3, 8)
        ind, outd = self.dir / "input", self.dir / "output"
        ind.mkdir(); outd.mkdir()
        write_pulsar2_run_input(ind, "input", arr)
        self.assertTrue((ind / "input.bin").is_file())
        self.assertEqual((ind / "input.bin").read_bytes()[:4], arr.tobytes()[:4])
        (outd / "logits.bin").write_bytes(arr.tobytes())
        got = read_pulsar2_run_output(outd, "logits", arr.shape)
        np.testing.assert_array_equal(got, arr)

    def test_ax_run_model_input_list_and_output(self):
        arr = np.random.rand(1, 3, 4).astype(np.float32)
        ind, outd = self.dir / "board_input", self.dir / "board_output"
        ind.mkdir(); outd.mkdir()
        write_ax_run_model_input(ind, "input", arr)
        self.assertEqual((ind / "input_list.txt").read_text(), "input.bin\n")
        self.assertTrue((ind / "input.bin").is_file())
        # 多输出/多文件时取第一个（按文件名排序）
        (outd / "z_other.bin").write_bytes(np.zeros(3, dtype=np.float32).tobytes())
        (outd / "a_logits.bin").write_bytes(arr.tobytes())
        got = read_ax_run_model_output(outd, arr.shape)
        np.testing.assert_array_equal(got, arr)
        # 无输出必须报错而不是静默返回
        empty = self.dir / "empty_out"; empty.mkdir()
        with self.assertRaises(RuntimeError):
            read_ax_run_model_output(empty, arr.shape)

    def test_raw_float32_helpers(self):
        arr = np.random.rand(6).astype(np.float32)
        p = self.dir / "raw.bin"
        write_raw_float32(p, arr)
        np.testing.assert_array_equal(read_raw_float32(p, (2, 3)), arr.reshape(2, 3))

    def test_calibration_tar_pack(self):
        samples = [np.random.rand(1, 4).astype(np.float32) for _ in range(3)]
        npy_dir = self.dir / "npy"; npy_dir.mkdir()
        for i, s in enumerate(samples):
            np.save(npy_dir / f"{i:04d}.npy", s)
        tar_path = self.dir / "input.tar.gz"
        pack_calibration_npy(npy_dir.glob("*.npy"), tar_path)
        with tarfile.open(tar_path, "r:gz") as tar:
            names = sorted(tar.getnames())
        self.assertEqual(names, ["0000.npy", "0001.npy", "0002.npy"])


if __name__ == "__main__":
    unittest.main()
