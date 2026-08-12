"""AX 推理输入/输出格式单一来源（成功案例固化）。

本模块把仓库内验证过的格式集中到一处，禁止在别处再发明新格式：

- pulsar2 run（仿真）: 输入 ``{input_name}.bin``（float32 raw），输出 ``{output_name}.bin``（float32 raw）
  - 文件名必须与 ONNX 输入/输出 tensor 名一致（Pulsar2 官方要求）
- ax_run_model（板端）: ``{input_name}.bin`` + ``input_list.txt``（每行一个 bin 文件名），输出目录下 ``*.bin``
- 校准数据（Numpy）: tar/tar.gz 内含 ``.npy``，float32、带 batch 维、与模型输入 shape 一致

成功案例与官方文档依据见 ``docs/input-format-cheatsheet.md``。
"""
import io
from pathlib import Path

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


def validate_calibration_archive(
    archive_path,
    tensor_name: str,
    expected_shape,
    expected_dtype=np.float32,
    min_samples: int = 1,
    max_check: int = 8,
) -> dict:
    """校验 Numpy 校准 tar/tar.gz 内容是否与模型输入一致（COMPILE 前预检）。

    规则（与 docs/input-format-cheatsheet.md 一致）：
    - tar 内含 ``.npy`` 文件（float32、带 batch 维、shape 与 input_shapes 一致）
    - 样本数至少 ``min_samples``（一般传 calibration_size；Pulsar2 会对
      calibration_size 与数据集大小取 min，样本不足只会警告不会失败）
    - ``tensor_name`` 仅用于错误提示，不检查文件名

    Returns:
        {"samples": int, "errors": [str], "warnings": [str]}
    """
    import tarfile

    result: dict = {"samples": 0, "errors": [], "warnings": []}
    path = Path(archive_path)
    if not path.is_file():
        result["errors"].append(
            f"校准包不存在: {path}（应先生成校准数据，参考 "
            "docs/input-format-cheatsheet.md §1）"
        )
        return result
    try:
        tar = tarfile.open(path, "r:*")
    except (tarfile.TarError, OSError) as e:
        result["errors"].append(f"校准包不是合法 tar/tar.gz: {path}（{e}）")
        return result
    with tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".npy")]
        if not members:
            result["errors"].append(
                f"校准包内没有 .npy 文件: {path}（Numpy 格式要求 tar 内含 npy）"
            )
            return result
        result["samples"] = len(members)
        if result["samples"] < min_samples:
            result["errors"].append(
                f"校准样本数 {result['samples']} < 要求 {min_samples}（{path}）"
            )
        exp_shape = tuple(int(d) for d in expected_shape)
        for m in members[:max_check]:
            try:
                f = tar.extractfile(m)
                arr = np.load(io.BytesIO(f.read()), allow_pickle=False)
            except Exception as e:
                result["errors"].append(f"npy 无法读取: {m.name}（{e}）")
                continue
            if tuple(arr.shape) != exp_shape:
                result["errors"].append(
                    f"npy shape 不符: {m.name} shape={tuple(arr.shape)}，"
                    f"期望 {exp_shape}（样本必须带 batch 维且与 input_shapes 完全一致）"
                )
            if arr.dtype != np.dtype(expected_dtype):
                result["errors"].append(
                    f"npy dtype 不符: {m.name} dtype={arr.dtype}，期望 {np.dtype(expected_dtype)}"
                )
        if len(members) > max_check:
            result["warnings"].append(
                f"仅抽查前 {max_check} 个样本（共 {len(members)} 个），其余未逐个体检"
            )
    return result


def assert_calibration_archive_ok(
    archive_path,
    tensor_name: str,
    expected_shape,
    expected_dtype=np.float32,
    min_samples: int = 1,
) -> int:
    """校准包预检的硬 gate：不通过直接抛 RuntimeError（带修复提示）。"""
    res = validate_calibration_archive(
        archive_path, tensor_name, expected_shape, expected_dtype, min_samples
    )
    if res["errors"]:
        raise RuntimeError(
            "校准数据预检未通过（" + "; ".join(res["errors"]) + "）\n"
            "修复提示: 重新生成校准包（scripts/export_onnx.py 或 run_generic(calibration_data=...)，"
            "样本 float32、带 batch 维、shape 与 ONNX 输入一致）"
        )
    return res["samples"]
