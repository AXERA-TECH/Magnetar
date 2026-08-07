"""PACKAGE: 组装面向小白的客户交付包。

核心原则：
- README 面向零基础用户，尽量简洁，一句话能跑起来
- 提供 setup.sh（一键装环境）和 run.sh（一键跑推理）
- assemble 完成后自动 self_test——模拟小白只看 README 复现，错则改之
"""
import json, os, shutil, subprocess, sys, tempfile, textwrap
from pathlib import Path


def assemble(task_dir: Path, metrics: dict, pulsar_image: str,
             model_name: str = "mobilenet_v2", labels=None) -> Path:
    """组装交付包，返回 package 目录路径。"""
    pkg = task_dir / "package"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True, exist_ok=True)

    # ---- models ----
    (pkg / "models").mkdir(exist_ok=True)
    shutil.copy2(task_dir / "compile" / "model.axmodel", pkg / "models" / "model.axmodel")
    _copy_if_exists(task_dir / "compile" / "model.axmodel.tar.gz", pkg / "models" / "model.axmodel.tar.gz")
    meta_src = task_dir / "export" / "model_meta.json"
    if meta_src.exists():
        shutil.copy2(meta_src, pkg / "models" / "model_meta.json")

    # ---- python SDK ----
    py_src = task_dir / "sdk" / "python"
    has_py = py_src.exists()
    if has_py:
        shutil.copytree(py_src, pkg / "python", dirs_exist_ok=True)
        # 端到端 NPU 已跑通（runonboard_report 存在）→ 发布包内 SDK 去掉
        # onnxruntime/torch/transformers 回退，只保留 AX 芯片推理路径。
        npu_verified = (task_dir / "runonboard" / "runonboard_report.md").is_file()
        if npu_verified:
            from magnetar.stages.sdk_gen import make_npu_only_sdk_dir
            make_npu_only_sdk_dir(pkg / "python")
            # 交付约束：端到端 NPU 跑通后禁止 CPU 回退，校验交付 SDK 依赖最小化
            # 匹配真实 import（避免命中说明文案里的字样，如 NPU-only 模板的报错提示）
            forbidden = (
                "import onnxruntime", "from onnxruntime",
                "import torch", "from torch",
                "import transformers", "from transformers",
            )
            leaked = [
                str(inf.relative_to(pkg))
                for inf in (pkg / "python").glob("*_sdk/inference.py")
                if any(f in inf.read_text(encoding="utf-8") for f in forbidden)
            ]
            if leaked:
                raise RuntimeError(
                    f"交付包 SDK 仍含 CPU 回退依赖（{leaked}），违反最小依赖/端到端 NPU 约束；"
                    "请用 run_generic_python(strict_npu=True) 重新生成"
                )
            (pkg / "NPU_ONLY_SDK.md").write_text(
                "本交付包已通过端到端 NPU 验证，Python SDK 仅依赖 pyaxengine，"
                "不含 onnxruntime/torch/transformers 等运行时回退。\n",
                encoding="utf-8",
            )

    # ---- cpp SDK ----
    cpp_src = task_dir / "sdk" / "cpp"
    has_cpp = cpp_src.exists()
    if has_cpp:
        shutil.copytree(cpp_src, pkg / "cpp", dirs_exist_ok=True)

    # ---- model_convert (可复现) ----
    mc = pkg / "model_convert"
    mc.mkdir(exist_ok=True)
    _copy_if_exists(task_dir / "compile" / "pulsar2_config.json", mc / "pulsar2_config.json")
    _copy_if_exists(task_dir / "export" / "model_meta.json", mc / "model_meta.json")
    _copy_if_exists(task_dir / "export" / "model.onnx", mc / "model.onnx")
    _copy_if_exists(task_dir / "export" / "export_onnx.py", mc / "export_onnx.py")
    # 旁路脚本等辅助文件
    for f in (task_dir / "export").glob("*.py"):
        if f.name != "export_onnx.py":
            _copy_if_exists(f, mc / f.name)

    (mc / "compile_pulsar2.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\npulsar2 build --config pulsar2_config.json\n",
        encoding="utf-8")
    os.chmod(mc / "compile_pulsar2.sh", 0o755)
    (mc / "README.md").write_text(
        f"# Model Convert\n\n原始编译使用 Docker 镜像 `{pulsar_image}`。\n", encoding="utf-8")

    # ---- reports ----
    reports = pkg / "reports"
    reports.mkdir(exist_ok=True)
    for rn in ["export_report.md", "compile_report.md", "simulate_report.md"]:
        stage = "export" if "export" in rn else "compile" if "compile" in rn else "simulate"
        _copy_if_exists(task_dir / stage / rn, reports / rn)
    _copy_if_exists(task_dir / "runonboard" / "runonboard_report.md", reports / "runonboard_report.md")

    # ---- 一键脚本 ----
    _write_setup_sh(pkg, has_py=has_py, has_cpp=has_cpp)
    _write_run_sh(pkg, model_name=model_name, has_py=has_py, has_cpp=has_cpp)

    # ---- README ----
    _write_readme(pkg, model_name=model_name, metrics=metrics, pulsar_image=pulsar_image,
                  has_py=has_py, has_cpp=has_cpp)

    # ---- .gitignore ----
    (pkg / ".gitignore").write_text(
        "__pycache__/\n*.pyc\nbuild/\nCMakeFiles/\nCMakeCache.txt\n*.egg-info/\n", encoding="utf-8")

    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "PACKAGE", artifacts={"package": str(pkg)},
               summary=f"交付包 {pkg.name}")
    return pkg


def self_test(pkg: Path, model_name: str = "model") -> dict:
    """模拟小白用户只看 README 复现一遍。

    在临时目录中：
    1. 跑 setup.sh
    2. 跑 run.sh
    返回 {"ok": bool, "output": str, "errors": list}
    """
    tmp = Path(tempfile.mkdtemp(prefix="magnetar_pkg_test_"))
    results = {"ok": False, "output": "", "errors": []}
    try:
        # 复制包到临时目录
        shutil.copytree(pkg, tmp / "package", dirs_exist_ok=True)
        test_dir = tmp / "package"

        # Step 1: setup.sh
        setup_script = test_dir / "setup.sh"
        if setup_script.exists():
            proc = subprocess.run(
                ["bash", str(setup_script)],
                cwd=str(test_dir), capture_output=True, text=True, timeout=120)
            results["output"] += f"[setup.sh stdout]\n{proc.stdout}\n[setup.sh stderr]\n{proc.stderr}\n"
            if proc.returncode != 0:
                results["errors"].append(f"setup.sh 失败 (exit {proc.returncode})")
                return results

        # Step 2: run.sh
        run_script = test_dir / "run.sh"
        if run_script.exists():
            proc = subprocess.run(
                ["bash", str(run_script)],
                cwd=str(test_dir), capture_output=True, text=True, timeout=120)
            results["output"] += f"[run.sh stdout]\n{proc.stdout}\n[run.sh stderr]\n{proc.stderr}\n"
            if proc.returncode != 0:
                results["errors"].append(f"run.sh 失败 (exit {proc.returncode})")
                return results

        results["ok"] = True
        return results
    except subprocess.TimeoutExpired:
        results["errors"].append("self_test 超时")
        return results
    except Exception as e:
        results["errors"].append(f"self_test 异常: {e}")
        return results
    finally:
        # 保留临时目录以便排查，但标记为可清理
        pass


# ---- 内部辅助 ----

def _copy_if_exists(src: Path, dst: Path):
    if src.exists():
        shutil.copy2(src, dst)


def _write_setup_sh(pkg: Path, has_py: bool, has_cpp: bool):
    """生成一键环境安装脚本。"""
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    lines.append('echo "=== 安装依赖 ==="')

    if has_py:
        py_req = pkg / "python" / "requirements.txt"
        if py_req.exists():
            lines.append(f"pip install -r python/requirements.txt")
        else:
            lines.append("pip install pyaxengine numpy")

    if has_cpp:
        lines.append("")
        lines.append('echo "C++ SDK: 请先安装 AX650 BSP SDK，然后："')
        lines.append("# export AX_RUNTIME_ROOT=/path/to/axruntime")
        lines.append("# mkdir -p cpp/build && cd cpp/build")
        lines.append('# cmake .. -DCMAKE_TOOLCHAIN_FILE=${AX_RUNTIME_ROOT}/toolchain.cmake')
        lines.append("# make -j$(nproc)")

    lines.append("")
    lines.append('echo "✅ 环境准备完成"')
    (pkg / "setup.sh").write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(pkg / "setup.sh", 0o755)


def _write_run_sh(pkg: Path, model_name: str, has_py: bool, has_cpp: bool):
    """生成一键推理脚本。"""
    lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
    lines.append('echo "=== 运行推理 ==="')

    if has_py:
        # 尽量生成可直接 copy 运行的 Python 推理代码
        demo_py = pkg / "python" / "demo.py"
        if not demo_py.exists():
            _write_demo_py(demo_py, model_name)
        lines.append("python python/demo.py")

    if has_cpp:
        lines.append("# ./cpp/build/model_example models/model.axmodel")

    (pkg / "run.sh").write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(pkg / "run.sh", 0o755)


def _write_demo_py(demo_py: Path, model_name: str):
    """生成一个最简单的推理 demo 脚本。"""
    demo_py.write_text(textwrap.dedent(f"""\
        '''{model_name} 推理 Demo——复制即用。'''
        import sys, os
        sys.path.insert(0, os.path.dirname(__file__))
        try:
            from {model_name.lower()}_sdk import ModelSDK
        except ImportError:
            print("请先安装 SDK: pip install -r requirements.txt")
            sys.exit(1)

        sdk = ModelSDK("models/model.axmodel")
        print("模型加载成功！")
        print(f"输入: {{sdk.input_info}}")
        print(f"输出: {{sdk.output_info}}")
    """), encoding="utf-8")


def _write_readme(pkg: Path, model_name: str, metrics: dict, pulsar_image: str,
                  has_py: bool, has_cpp: bool):
    """生成面向小白的简洁 README。"""
    cos = metrics.get("cosine_similarity", "N/A")
    latency = metrics.get("inference_latency_ms", "N/A")
    ax_size = "N/A"
    ax_path = pkg / "models" / "model.axmodel"
    if ax_path.exists():
        ax_size = f"{ax_path.stat().st_size / 1024 / 1024:.1f} MB"

    parts = [
        f"# {model_name} AXMODEL",
        "",
        f"精度 cosine ≈ {cos}  |  推理耗时 {latency} ms  |  模型大小 {ax_size}",
        "",
        "## 快速开始（只需两步）",
        "",
    ]

    if has_py:
        parts.extend([
            "### 1. 安装环境",
            "",
            "```bash",
            "bash setup.sh",
            "```",
            "",
            "### 2. 跑推理",
            "",
            "```bash",
            "bash run.sh",
            "```",
        ])
    else:
        parts.extend([
            "### 1. 部署 AXMODEL",
            "将 `models/model.axmodel` 部署到 AX 板。",
            "",
            "### 2. 链接 C++ SDK",
            "参考 `cpp/` 目录中的 CMake 配置。",
        ])

    parts.extend([
        "",
        "## 目录说明",
        "",
        "| 目录 | 用途 |",
        "|------|------|",
        "| `models/` | AXMODEL 模型文件 + 元信息 |",
    ])
    if has_py:
        parts.append("| `python/` | Python SDK（pyaxengine）|")
    if has_cpp:
        parts.append("| `cpp/` | C++ SDK（AX Engine runtime）|")
    parts.extend([
        "| `model_convert/` | 模型导出 & 编译脚本（可复现）|",
        "| `reports/` | 各阶段报告 |",
        "| `setup.sh` | 一键安装依赖 |",
        "| `run.sh` | 一键运行推理 |",
        "",
        "## 常见问题",
        "",
        "**Q: import 报错找不到 pyaxengine？**",
        "A: 运行 `bash setup.sh` 会自动安装。",
        "",
        "**Q: 怎么在自己的代码里用？**",
        "A: 参考 `python/demo.py`，核心就 3 行：",
        "",
        "```python",
        f"from {model_name.lower()}_sdk import ModelSDK",
        'sdk = ModelSDK("models/model.axmodel")',
        "result = sdk.run(your_input)",
        "```",
        "",
        f"**Q: 想自己重新编译？**",
        f"A: 进入 `model_convert/`，确保 Pulsar2 可用后运行 `bash compile_pulsar2.sh`。",
        f"   原始编译使用 Docker 镜像 `{pulsar_image}`。",
    ])

    (pkg / "README.md").write_text("\n".join(parts) + "\n", encoding="utf-8")
