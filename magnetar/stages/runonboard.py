"""RUNONBOARD: 板端部署和验证。"""
import json
import os
import shutil
from pathlib import Path

import numpy as np


def run(task_dir: Path, sample: np.ndarray, target_hardware: str, password: str) -> dict | None:
    """部署到 AX 板端并运行 SDK 验证。无可用板子返回 None。"""
    from magnetar.board_util import select_board, ssh, scp_to, scp_from
    from magnetar.docker_util import run as local_run

    board = select_board(target_hardware, password)
    if board is None:
        return None

    runonboard = task_dir / "runonboard"
    runonboard.mkdir(parents=True, exist_ok=True)

    input_npy = runonboard / "input.npy"
    input_bin = runonboard / "input.bin"
    np.save(input_npy, sample.astype(np.float32))
    sample.astype(np.float32).tofile(input_bin)

    # 获取 AX runtime 用于交叉编译
    runtime_root = task_dir / "cache" / "ax_runtime"
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    (runtime_root / "include").mkdir(parents=True, exist_ok=True)
    (runtime_root / "lib").mkdir(parents=True, exist_ok=True)
    scp_from(board, "/soc/lib/libax_engine.so", runtime_root / "lib" / "libax_engine.so")
    scp_from(board, "/soc/lib/libax_sys.so", runtime_root / "lib" / "libax_sys.so")
    scp_from(board, "/soc/include", runtime_root / "include_parent")
    include_parent = runtime_root / "include_parent"
    if (include_parent / "include").is_dir():
        shutil.copytree(include_parent / "include", runtime_root / "include", dirs_exist_ok=True)
        shutil.rmtree(include_parent)
    elif (include_parent / "ax_engine_api.h").is_file():
        shutil.copytree(include_parent, runtime_root / "include", dirs_exist_ok=True)
        shutil.rmtree(include_parent)

    # 交叉编译 C++ SDK
    aarch64_gxx = os.environ.get("AARCH64_GXX")
    if aarch64_gxx:
        cpp = task_dir / "sdk" / "cpp"
        build_dir = cpp / "build-aarch64"
        build_dir.mkdir(exist_ok=True)
        local_run([
            "cmake", "-S", str(cpp), "-B", str(build_dir),
            f"-DCMAKE_TOOLCHAIN_FILE={cpp}/toolchain-aarch64.cmake",
            f"-DAX_RUNTIME_ROOT={runtime_root}",
        ], timeout=180)
        local_run(["cmake", "--build", str(build_dir)], timeout=180)
        cpp_binary = build_dir / "mobilenet_example"
        if not cpp_binary.exists():
            cpp_binary = next(build_dir.glob("*/mobilenet_example"), None)
    else:
        cpp_binary = Path("/tmp/magnetar_mobilenet_example")

    # 部署到板端
    remote_dir = f"/tmp/magnetar_{os.getpid()}"
    ssh(board, f"rm -rf {remote_dir} && mkdir -p {remote_dir}")
    scp_to(board, task_dir / "package", f"{remote_dir}/package")
    scp_to(board, input_npy, f"{remote_dir}/input.npy")
    scp_to(board, input_bin, f"{remote_dir}/input.bin")
    if cpp_binary and cpp_binary.exists():
        scp_to(board, cpp_binary, f"{remote_dir}/mobilenet_example")
        ssh(board, f"chmod +x {remote_dir}/mobilenet_example")

    # Python SDK
    py_log = ssh(board,
        f"cd {remote_dir} && "
        "LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/package/python "
        "python3 package/python/mobilenet_sdk/example.py "
        "--model package/models/model.axmodel --input input.npy --output python_output.npy",
        timeout=240)

    # C++ SDK
    cpp_log = ""
    if cpp_binary and cpp_binary.exists():
        cpp_log = ssh(board,
            f"cd {remote_dir} && LD_LIBRARY_PATH=/soc/lib "
            "./mobilenet_example package/models/model.axmodel input.bin cpp_output.bin "
            "package/cpp/imagenet_classes.txt",
            timeout=240)

    scp_from(board, f"{remote_dir}/python_output.npy", runonboard / "python_output.npy")
    if cpp_binary and cpp_binary.exists():
        scp_from(board, f"{remote_dir}/cpp_output.bin", runonboard / "cpp_output.bin")

    python_output = np.load(runonboard / "python_output.npy").astype(np.float32)
    from magnetar.stages.simulate import cosine
    board_metrics = {
        "board": board["host"],
        "chip_type": board["chip_type"],
        "python_shape": list(python_output.shape),
    }
    if cpp_binary and cpp_binary.exists():
        cpp_output = np.fromfile(
            runonboard / "cpp_output.bin", dtype=np.float32).reshape(python_output.shape)
        board_metrics["cpp_shape"] = list(cpp_output.shape)
        board_metrics["python_cpp_cosine"] = cosine(python_output, cpp_output)
        board_metrics["python_cpp_mae"] = float(np.mean(np.abs(python_output - cpp_output)))

    (runonboard / "runonboard_report.md").write_text(
        "# Run On Board Report\n\n" +
        "\n".join(f"- {k}: {v}" for k, v in board_metrics.items()) +
        f"\n\n## Python SDK Log\n\n```text\n{py_log[-4000:]}\n```" +
        f"\n\n## C++ SDK Log\n\n```text\n{cpp_log[-4000:]}\n```",
        encoding="utf-8")

    shutil.copy2(runonboard / "runonboard_report.md",
                 task_dir / "package" / "reports" / "runonboard_report.md")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"\n- RUNONBOARD: {board['host']} {board['chip_type']}\n")

    return board_metrics
