"""AX 推理输入/输出格式单一来源（成功案例固化）。

本模块把仓库内验证过的格式集中到一处，禁止在别处再发明新格式：

- pulsar2 run（仿真）: 输入 ``{input_name}.bin``（float32 raw），输出 ``{output_name}.bin``（float32 raw）
  - 文件名必须与 ONNX 输入/输出 tensor 名一致（Pulsar2 官方要求）
- ax_run_model（板端）: ``{input_name}.bin`` + ``input_list.txt``（每行一个 bin 文件名），输出目录下 ``*.bin``
- 校准数据（Numpy）: tar/tar.gz 内含 ``.npy``，float32、带 batch 维、与模型输入 shape 一致

成功案例与官方文档依据见 ``docs/input-format-cheatsheet.md``。
"""
import numpy as np


def write_raw_float32(path, array) -> None:
    """写 float32 连续内存 raw bin（pulsar2 run / ax_run_model 通用输入）。"""
    np.ascontiguousarray(array, dtype=np.float32).tofile(path)


def read_raw_float32(path, shape) -> np.ndarray:
    """读 float32 raw bin 并按给定 shape 还原。"""
    return np.fromfile(path, dtype=np.float32).reshape(shape)


def write_pulsar2_run_input(directory, input_name: str, array) -> None:
    """写 pulsar2 run 输入：``<directory>/<input_name>.bin``。"""
    write_raw_float32(directory / f"{input_name}.bin", array)


def read_pulsar2_run_output(directory, output_name: str, shape) -> np.ndarray:
    """读 pulsar2 run 输出：``<directory>/<output_name>.bin``。"""
    return read_raw_float32(directory / f"{output_name}.bin", shape)


def write_ax_run_model_input(directory, input_name: str, array) -> None:
    """写 ax_run_model 输入：``<input_name>.bin`` + ``input_list.txt``（每行一个 bin 文件名）。"""
    write_raw_float32(directory / f"{input_name}.bin", array)
    (directory / "input_list.txt").write_text(f"{input_name}.bin\n", encoding="utf-8")


def read_ax_run_model_output(directory, shape) -> np.ndarray:
    """读 ax_run_model 输出：取输出目录下第一个 ``*.bin``（单输出模型）。"""
    bins = sorted(directory.glob("*.bin"))
    if not bins:
        raise RuntimeError(f"ax_run_model 未产生输出: {directory}")
    return read_raw_float32(bins[0], shape)


def pack_calibration_npy(files, tar_path) -> None:
    """把 npy 样本打包成校准 tar（arcname 取文件名本身，如 0000.npy）。"""
    import tarfile
    with tarfile.open(tar_path, "w:gz") as tar:
        for npy in sorted(files):
            tar.add(npy, arcname=npy.name)
