"""PACKAGE: 组装客户交付包。"""
import json
import os
import shutil
import textwrap
from pathlib import Path


def assemble(task_dir: Path, metrics: dict, pulsar_image: str,
             model_name: str = "mobilenet_v2", imagenet_labels: list[str] | None = None) -> Path:
    """组装 package/ 交付包目录。"""
    package = task_dir / "package"
    package.mkdir(parents=True, exist_ok=True)

    # models/
    (package / "models").mkdir(exist_ok=True)
    shutil.copy2(task_dir / "compile" / "model.axmodel", package / "models" / "model.axmodel")
    shutil.copy2(task_dir / "export" / "model_meta.json", package / "models" / "model_meta.json")

    # python/
    py_src = task_dir / "sdk" / "python"
    py_dst = package / "python"
    if py_src.exists():
        shutil.copytree(py_src, py_dst, dirs_exist_ok=True)

    # cpp/
    cpp_src = task_dir / "sdk" / "cpp"
    cpp_dst = package / "cpp"
    if cpp_src.exists():
        shutil.copytree(cpp_src, cpp_dst, dirs_exist_ok=True)

    # model_convert/
    mc = package / "model_convert"
    mc.mkdir(exist_ok=True)
    _write_export_script(mc, model_name)
    shutil.copy2(task_dir / "compile" / "pulsar2_config.json", mc / "pulsar2_config.json")
    shutil.copy2(task_dir / "export" / "model_meta.json", mc / "model_meta.json")
    (mc / "compile_pulsar2.sh").write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
        set -euo pipefail
        pulsar2 build --config pulsar2_config.json
    """), encoding="utf-8")
    os.chmod(mc / "compile_pulsar2.sh", 0o755)
    (mc / "README.md").write_text(textwrap.dedent(f"""\
        # Model Convert

        - `export_onnx.py`: exports {model_name} to static ONNX.
        - `pulsar2_config.json`: Pulsar2 build config.
        - `compile_pulsar2.sh`: minimal build command.
        - `model_meta.json`: input/output metadata.

        Original compile used Docker image `{pulsar_image}`.
    """), encoding="utf-8")

    # reports/
    reports = package / "reports"
    reports.mkdir(exist_ok=True)
    for src_name in ["export_report.md", "compile_report.md", "simulate_report.md"]:
        src = task_dir / "export" / src_name if "export" in src_name else \
              task_dir / "compile" / src_name if "compile" in src_name else \
              task_dir / "simulate" / src_name
        if src.exists():
            shutil.copy2(src, reports / src_name)

    runonboard_report = task_dir / "runonboard" / "runonboard_report.md"
    if runonboard_report.exists():
        shutil.copy2(runonboard_report, reports / "runonboard_report.md")

    # README
    _write_package_readme(package, model_name, pulsar_image, metrics)

    # .gitignore
    (package / ".gitignore").write_text(textwrap.dedent("""\
        __pycache__/
        *.pyc
        build/
        build-*/
        CMakeFiles/
        CMakeCache.txt
        cmake_install.cmake
        Makefile
        *_output.npy
        *_output.bin
    """), encoding="utf-8")

    return package


def _write_export_script(mc: Path, model_name: str) -> None:
    if "mobilenet" in model_name.lower():
        (mc / "export_onnx.py").write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import argparse, numpy as np, torch
            from torchvision.models import mobilenet_v2, MobileNet_V2_Weights

            def main():
                parser = argparse.ArgumentParser()
                parser.add_argument("--output", default="model.onnx")
                args = parser.parse_args()
                model = mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT).eval()
                sample = torch.rand(1, 3, 224, 224, dtype=torch.float32)
                torch.onnx.export(model, sample, args.output,
                    input_names=["input"], output_names=["logits"],
                    opset_version=17, dynamo=False)

            if __name__ == "__main__":
                main()
        """), encoding="utf-8")
    else:
        (mc / "export_onnx.py").write_text(
            f"# Export script for {model_name}\n# TODO: implement ONNX export\n",
            encoding="utf-8")


def _write_package_readme(package: Path, model_name: str, pulsar_image: str, metrics: dict) -> None:
    cos = metrics.get("cosine_similarity", "N/A")
    (package / "README.md").write_text(textwrap.dedent(f"""\
        # {model_name} AXMODEL Project

        - target: AX650
        - pulsar2_image: {pulsar_image}
        - cosine_similarity: {cos}

        This is a standalone customer project.

        ## Layout

        - `models/`: AXMODEL and model metadata.
        - `python/`: Python SDK using `pyaxengine`.
        - `cpp/`: C++ SDK using AX Engine runtime.
        - `model_convert/`: ONNX export, Pulsar2 config, conversion notes.
        - `reports/`: export, compile, simulate, and run-on-board reports.

        ## Python

        ```bash
        LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/python \\
          python3 python/mobilenet_sdk/example.py \\
          --model models/model.axmodel --input input.npy --output output.npy
        ```

        ## C++

        ```bash
        cmake -S cpp -B cpp/build-aarch64 \\
          -DCMAKE_TOOLCHAIN_FILE=cpp/toolchain-aarch64.cmake \\
          -DAX_RUNTIME_ROOT=/path/to/ax/runtime
        cmake --build cpp/build-aarch64
        ```

        ## Model Conversion

        See `model_convert/README.md` for the full conversion recipe.
    """), encoding="utf-8")
