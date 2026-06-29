import json
import os
import re
import shutil
import subprocess
import tarfile
import textwrap
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
import yaml
from torchvision.models import MobileNet_V2_Weights, mobilenet_v2


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / "workflows" / "magnetar.yaml"
TASK_DIR = Path(
    os.environ.get(
        "MAGNETAR_MOBILENET_TASK_DIR",
        REPO_ROOT / "todos" / "work" / "unittest-mobilenet-real",
    )
)
TARGET_HARDWARE = os.environ.get("MAGNETAR_TARGET_HARDWARE", "AX650")
BOARD_DASHBOARD_URL = os.environ.get(
    "MAGNETAR_BOARD_DASHBOARD", "http://10.126.35.22:25000/api/devices"
)
BOARD_PASSWORD = os.environ.get("MAGNETAR_BOARD_PASSWORD", "123456")
PYAXENGINE_REPO = Path(os.environ.get("PYAXENGINE_REPO", "/tmp/pyaxengine"))


def run(cmd, cwd=REPO_ROOT, timeout=600):
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "command failed with exit code {}\n{}\n{}".format(
                proc.returncode, " ".join(map(str, cmd)), proc.stdout
            )
        )
    return proc.stdout


def latest_pulsar2_image():
    try:
        output = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=30)
    except Exception as exc:
        raise unittest.SkipTest(f"Docker is unavailable: {exc}") from exc

    candidates = []
    for image in output.splitlines():
        repo, _, tag = image.partition(":")
        if repo != "pulsar2":
            continue
        match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:-|$)", tag)
        if not match:
            continue
        version = tuple(int(part or 0) for part in match.groups())
        candidates.append((version, image))
    if not candidates:
        raise unittest.SkipTest("No local pulsar2:* Docker image found")
    return max(candidates, key=lambda item: item[0])[1]


def docker_pulsar2(image, workspace, command, timeout=1200):
    uid = os.getuid()
    gid = os.getgid()
    wrapped = (
        "set +e; "
        f"PATH=/usr/local/bin/.venv/bin:/opt/pulsar2:$PATH {command}; "
        "status=$?; "
        f"chown -R {uid}:{gid} /workspace; "
        "exit $status"
    )
    return run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workspace}:/workspace",
            image,
            "-lc",
            wrapped,
        ],
        timeout=timeout,
    )


def make_task_dir_writable(task_dir):
    if not task_dir.exists():
        return
    image = latest_pulsar2_image()
    uid = os.getuid()
    gid = os.getgid()
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{task_dir}:/workspace",
            image,
            "-lc",
            f"chown -R {uid}:{gid} /workspace",
        ],
        timeout=120,
    )


class MobileNetRealWorkflowTest(unittest.TestCase):
    def test_real_mobilenet_download_export_compile_simulate_and_package(self):
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["workflow"]
        self.assertEqual(workflow["name"], "magnetar")
        self.assertIn(
            "package/models/model.axmodel",
            "\n".join(workflow["completion"]["success_when"]),
        )

        pulsar_image = latest_pulsar2_image()
        self.assertTrue(pulsar_image.startswith("pulsar2:"))

        make_task_dir_writable(TASK_DIR)
        if TASK_DIR.exists():
            shutil.rmtree(TASK_DIR)
        self._init_task_dir(TASK_DIR, pulsar_image)

        model, sample = self._download_and_export_mobilenet(TASK_DIR)
        self._validate_onnx_and_metadata(TASK_DIR, model, sample)
        self._generate_calibration_data(TASK_DIR, sample)
        self._compile_axmodel(TASK_DIR, pulsar_image)
        metrics = self._simulate_and_compare(TASK_DIR, pulsar_image, sample)
        self.assertGreaterEqual(metrics["cosine_similarity"], 0.98)
        self._generate_sdks_and_package(TASK_DIR, metrics, pulsar_image)
        board_metrics = self._run_onboard(TASK_DIR, sample)
        self.assertGreaterEqual(board_metrics["python_cpp_cosine"], 0.98)
        self._assert_package_contract(TASK_DIR)

    def _init_task_dir(self, task_dir, pulsar_image):
        for name in [
            "origin",
            "export",
            "compile",
            "simulate",
            "sdk/python/mobilenet_sdk",
            "sdk/cpp",
            "runonboard",
            "package",
            "cache",
        ]:
            (task_dir / name).mkdir(parents=True, exist_ok=True)
        (task_dir / "task.md").write_text(
            textwrap.dedent(
                f"""\
                # MobileNet Real Workflow Test

                - SOURCE: torchvision.models.mobilenet_v2(weights=DEFAULT)
                - TARGET_HARDWARE: {TARGET_HARDWARE}
                - PULSAR2_IMAGE: {pulsar_image}
                - STATUS: INIT
                """
            ),
            encoding="utf-8",
        )
        (task_dir / "analysis.md").write_text(
            "真实集成测试：下载 MobileNetV2 权重，导出 ONNX，编译 AXMODEL，仿真并打包。\n",
            encoding="utf-8",
        )

    def _download_and_export_mobilenet(self, task_dir):
        export_dir = task_dir / "export"
        weights = MobileNet_V2_Weights.DEFAULT
        model = mobilenet_v2(weights=weights).eval()
        sample = torch.rand(1, 3, 224, 224, dtype=torch.float32)

        with torch.no_grad():
            torch_output = model(sample).detach().cpu().numpy()
        np.save(export_dir / "source_output.npy", torch_output.astype(np.float32))
        np.save(export_dir / "sample_input.npy", sample.numpy().astype(np.float32))

        onnx_path = export_dir / "model.onnx"
        torch.onnx.export(
            model,
            sample,
            onnx_path,
            input_names=["input"],
            output_names=["logits"],
            opset_version=17,
            dynamo=False,
        )

        (export_dir / "export-static-onnx.py").write_text(
            "from torchvision.models import mobilenet_v2, MobileNet_V2_Weights\n",
            encoding="utf-8",
        )
        (export_dir / "export_report.md").write_text(
            "# Export Report\n\nDownloaded torchvision MobileNetV2 weights and exported static ONNX.\n",
            encoding="utf-8",
        )
        with (task_dir / "task.md").open("a", encoding="utf-8") as f:
            f.write(f"\n- EXPORT: {onnx_path}\n")
        return model, sample.numpy().astype(np.float32)

    def _validate_onnx_and_metadata(self, task_dir, model, sample):
        export_dir = task_dir / "export"
        onnx_path = export_dir / "model.onnx"
        onnx_model = onnx.load(onnx_path)
        onnx.checker.check_model(onnx_model)

        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        onnx_output = sess.run(None, {"input": sample})[0].astype(np.float32)
        with torch.no_grad():
            torch_output = model(torch.from_numpy(sample)).detach().cpu().numpy().astype(np.float32)

        cosine = self._cosine(torch_output, onnx_output)
        self.assertGreaterEqual(cosine, 0.999)

        model_meta = {
            "model_name": "mobilenet_v2",
            "framework": "torchvision",
            "inputs": [
                {
                    "name": "input",
                    "shape": [1, 3, 224, 224],
                    "dtype": "float32",
                    "layout": "NCHW",
                    "preprocess": "test uses already-normalized float32 tensor input",
                }
            ],
            "outputs": [
                {
                    "name": "logits",
                    "shape": [1, 1000],
                    "dtype": "float32",
                    "semantic": "ImageNet logits",
                }
            ],
            "opset": 17,
            "torch_onnx_cosine": cosine,
        }
        (export_dir / "model_meta.json").write_text(
            json.dumps(model_meta, indent=2), encoding="utf-8"
        )

    def _generate_calibration_data(self, task_dir, sample):
        calib_input = task_dir / "export" / "calib_data" / "input"
        calib_input.mkdir(parents=True, exist_ok=True)
        for idx in range(4):
            data = np.clip(sample + (idx * 0.01), 0, 1).astype(np.float32)
            np.save(calib_input / f"{idx:04d}.npy", data)

        tar_path = task_dir / "export" / "calib_data" / "input.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            for npy in sorted(calib_input.glob("*.npy")):
                tar.add(npy, arcname=npy.name)

    def _compile_axmodel(self, task_dir, pulsar_image):
        config = {
            "input": "/workspace/export/model.onnx",
            "output_dir": "/workspace/compile",
            "output_name": "model.axmodel",
            "work_dir": "/workspace/compile/work",
            "model_type": "ONNX",
            "target_hardware": TARGET_HARDWARE,
            "npu_mode": "NPU1",
            "input_shapes": "input:1x3x224x224",
            "onnx_opt": {
                "disable_onnx_optimization": False,
                "enable_onnxsim": False,
                "model_check": True,
            },
            "quant": {
                "input_configs": [
                    {
                        "tensor_name": "input",
                        "calibration_dataset": "/workspace/export/calib_data/input.tar.gz",
                        "calibration_format": "Numpy",
                        "calibration_size": 4,
                        "calibration_mean": [],
                        "calibration_std": [],
                    }
                ],
                "calibration_method": "MinMax",
                "precision_analysis": False,
                "precision_analysis_method": "PerLayer",
                "precision_analysis_mode": "Reference",
                "highest_mix_precision": False,
            },
            "input_processors": [
                {
                    "tensor_name": "input",
                    "tensor_format": "RGB",
                    "tensor_layout": "NCHW",
                    "src_format": "RGB",
                    "src_layout": "NCHW",
                    "src_dtype": "FP32",
                    "mean": [],
                    "std": [],
                }
            ],
        }
        config_path = task_dir / "compile" / "pulsar2_config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        log = docker_pulsar2(
            pulsar_image,
            task_dir,
            "pulsar2 build --config /workspace/compile/pulsar2_config.json",
            timeout=1800,
        )
        (task_dir / "compile" / "compile.log").write_text(log, encoding="utf-8")
        axmodel = task_dir / "compile" / "model.axmodel"
        self.assertTrue(axmodel.is_file(), "Pulsar2 did not produce model.axmodel")
        self.assertGreater(axmodel.stat().st_size, 1024)
        (task_dir / "compile" / "compile_report.md").write_text(
            f"# Compile Report\n\n- image: {pulsar_image}\n- axmodel: {axmodel}\n",
            encoding="utf-8",
        )

    def _simulate_and_compare(self, task_dir, pulsar_image, sample):
        sim_dir = task_dir / "simulate"
        input_dir = sim_dir / "input"
        output_dir = sim_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        sample.astype(np.float32).tofile(input_dir / "input.bin")

        log = docker_pulsar2(
            pulsar_image,
            task_dir,
            "pulsar2 run --model /workspace/compile/model.axmodel "
            "--input_dir /workspace/simulate/input "
            "--output_dir /workspace/simulate/output",
            timeout=900,
        )
        (sim_dir / "pulsar2_run.log").write_text(log, encoding="utf-8")

        sess = ort.InferenceSession(
            str(task_dir / "export" / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        onnx_output = sess.run(None, {"input": sample})[0].astype(np.float32)
        ax_output = np.fromfile(output_dir / "logits.bin", dtype=np.float32).reshape(1, 1000)

        metrics = {
            "cosine_similarity": self._cosine(onnx_output, ax_output),
            "mae": float(np.mean(np.abs(onnx_output - ax_output))),
            "max_abs_diff": float(np.max(np.abs(onnx_output - ax_output))),
        }
        (sim_dir / "simulate_report.md").write_text(
            "# Simulate Report\n\n"
            + "\n".join(f"- {key}: {value}" for key, value in metrics.items())
            + "\n",
            encoding="utf-8",
        )
        return metrics

    def _generate_sdks_and_package(self, task_dir, metrics, pulsar_image):
        imagenet_labels = MobileNet_V2_Weights.DEFAULT.meta["categories"]
        py_sdk = task_dir / "sdk" / "python" / "mobilenet_sdk"
        py_sdk.mkdir(parents=True, exist_ok=True)
        (py_sdk / "__init__.py").write_text(
            "from .inference import MobileNetClassifier\n", encoding="utf-8"
        )
        (py_sdk / "inference.py").write_text(
            textwrap.dedent(
                """\
                import numpy as np
                from .postprocess import topk


                DEFAULT_PROVIDER = "AxEngineExecutionProvider"


                class MobileNetClassifier:
                    def __init__(self, model_path, providers=None, labels=None):
                        import axengine as axe

                        self.model_path = model_path
                        self.labels = labels
                        preferred = providers or [DEFAULT_PROVIDER]
                        try:
                            self.session = axe.InferenceSession(model_path, providers=preferred)
                        except Exception:
                            available = list(axe.get_available_providers())
                            fallback = [name for name in available if name not in preferred]
                            if not fallback:
                                raise
                            self.session = axe.InferenceSession(model_path, providers=[fallback[0]])
                        self.inputs = self.session.get_inputs()
                        self.outputs = self.session.get_outputs()

                    def run(self, input_tensor):
                        array = np.ascontiguousarray(input_tensor.astype(np.float32))
                        return self.session.run(None, {self.inputs[0].name: array})[0]

                    def classify(self, input_tensor, k=5):
                        logits = self.run(input_tensor)
                        return topk(logits, labels=self.labels, k=k)
                """
            ),
            encoding="utf-8",
        )
        (py_sdk / "example.py").write_text(
            textwrap.dedent(
                """\
                import argparse
                from pathlib import Path
                import numpy as np
                from mobilenet_sdk import MobileNetClassifier
                from mobilenet_sdk.postprocess import load_labels


                def main():
                    parser = argparse.ArgumentParser()
                    parser.add_argument("--model", required=True)
                    parser.add_argument("--input", required=True)
                    parser.add_argument("--output", required=True)
                    parser.add_argument("--labels", default=str(Path(__file__).resolve().parents[1] / "imagenet_classes.txt"))
                    parser.add_argument("--topk", type=int, default=5)
                    args = parser.parse_args()

                    labels = load_labels(args.labels)
                    classifier = MobileNetClassifier(args.model, labels=labels)
                    input_tensor = np.load(args.input)
                    logits = classifier.run(input_tensor)
                    np.save(args.output, logits.astype(np.float32))
                    for item in classifier.classify(input_tensor, k=args.topk):
                        print(f"{item['rank']}: {item['label']} ({item['score']:.6f})")


                if __name__ == "__main__":
                    main()
                """
            ),
            encoding="utf-8",
        )
        (py_sdk / "preprocess.py").write_text(
            "import numpy as np\n\n\ndef preprocess(array):\n    return np.ascontiguousarray(array.astype(np.float32))\n",
            encoding="utf-8",
        )
        (py_sdk / "postprocess.py").write_text(
            textwrap.dedent(
                """\
                import numpy as np


                def load_labels(path):
                    with open(path, "r", encoding="utf-8") as f:
                        return [line.strip() for line in f if line.strip()]


                def topk(logits, labels=None, k=5):
                    flat = logits.reshape(-1)
                    order = np.argsort(flat)[::-1][:k]
                    result = []
                    for rank, index in enumerate(order, start=1):
                        label = labels[int(index)] if labels and int(index) < len(labels) else str(int(index))
                        result.append(
                            {
                                "rank": rank,
                                "index": int(index),
                                "label": label,
                                "score": float(flat[index]),
                            }
                        )
                    return result
                """
            ),
            encoding="utf-8",
        )
        (task_dir / "sdk" / "python" / "imagenet_classes.txt").write_text(
            "\n".join(imagenet_labels) + "\n",
            encoding="utf-8",
        )
        (task_dir / "sdk" / "python" / "requirements.txt").write_text(
            "numpy\npyaxengine @ git+https://github.com/AXERA-TECH/pyaxengine.git\n",
            encoding="utf-8",
        )
        (task_dir / "sdk" / "python" / "README.md").write_text(
            textwrap.dedent(
                """\
                # Python SDK

                运行环境需要 AX 板端 `/soc/lib` 和 `pyaxengine`。默认 provider 为
                `AxEngineExecutionProvider`；不可用时 SDK 会尝试 pyaxengine 返回的其他 provider。

                ```bash
                LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/python \\
                  python3 python/mobilenet_sdk/example.py \\
                  --model models/model.axmodel --input input.npy --output output.npy
                ```

                该示例实例化 `MobileNetClassifier`，输出 ImageNet top-k 分类结果，
                同时保存 logits 方便与仿真结果对比。
                """
            ),
            encoding="utf-8",
        )

        cpp_sdk = task_dir / "sdk" / "cpp"
        (cpp_sdk / "include").mkdir(parents=True, exist_ok=True)
        (cpp_sdk / "src").mkdir(parents=True, exist_ok=True)
        (cpp_sdk / "examples").mkdir(parents=True, exist_ok=True)
        (cpp_sdk / "CMakeLists.txt").write_text(
            textwrap.dedent(
                """\
                cmake_minimum_required(VERSION 3.16)
                project(mobilenet_sdk)
                set(CMAKE_CXX_STANDARD 17)
                set(CMAKE_CXX_STANDARD_REQUIRED ON)
                set(AX_RUNTIME_ROOT "" CACHE PATH "AX board runtime root containing include/ and lib/")
                add_library(mobilenet_sdk src/mobilenet_runner.cpp)
                target_include_directories(mobilenet_sdk PUBLIC include)
                add_executable(mobilenet_example examples/main.cpp)
                if(AX_RUNTIME_ROOT)
                  target_include_directories(mobilenet_sdk PRIVATE ${AX_RUNTIME_ROOT}/include)
                  target_link_directories(mobilenet_sdk PRIVATE ${AX_RUNTIME_ROOT}/lib)
                  target_link_libraries(mobilenet_sdk PRIVATE ax_engine ax_sys)
                endif()
                target_link_libraries(mobilenet_example PRIVATE mobilenet_sdk)
                """
            ),
            encoding="utf-8",
        )
        (cpp_sdk / "include" / "mobilenet_runner.hpp").write_text(
            textwrap.dedent(
                """\
                #pragma once

                #include <string>
                #include <vector>


                struct Classification {
                    int rank;
                    int index;
                    float score;
                    std::string label;
                };


                class MobileNetRunner {
                public:
                    explicit MobileNetRunner(const std::string& model_path);
                    ~MobileNetRunner();

                    MobileNetRunner(const MobileNetRunner&) = delete;
                    MobileNetRunner& operator=(const MobileNetRunner&) = delete;

                    std::vector<float> run(const std::vector<float>& input);
                    std::vector<Classification> classify(
                        const std::vector<float>& input,
                        const std::vector<std::string>& labels,
                        int k = 5);

                private:
                    struct Impl;
                    Impl* impl_;
                };

                std::vector<float> read_float_file(const std::string& path);
                void write_float_file(const std::string& path, const std::vector<float>& values);
                std::vector<std::string> read_labels(const std::string& path);
                """
            ),
            encoding="utf-8",
        )
        (cpp_sdk / "src" / "mobilenet_runner.cpp").write_text(
            textwrap.dedent(
                """\
                #include "mobilenet_runner.hpp"

                #include <ax_engine_api.h>
                #include <ax_sys_api.h>

                #include <algorithm>
                #include <cstring>
                #include <fstream>
                #include <iterator>
                #include <numeric>
                #include <stdexcept>


                namespace {
                std::vector<char> read_binary(const std::string& path) {
                    std::ifstream file(path, std::ios::binary);
                    if (!file) {
                        throw std::runtime_error("failed to open " + path);
                    }
                    return std::vector<char>(
                        std::istreambuf_iterator<char>(file),
                        std::istreambuf_iterator<char>());
                }

                void check_ax(int ret, const char* message) {
                    if (ret != 0) {
                        throw std::runtime_error(message);
                    }
                }
                }  // namespace

                struct MobileNetRunner::Impl {
                    AX_ENGINE_HANDLE handle = nullptr;
                    AX_ENGINE_CONTEXT_T context = nullptr;
                    AX_ENGINE_IO_INFO_T* info = nullptr;
                    AX_ENGINE_IO_T io {};
                    std::vector<AX_ENGINE_IO_BUFFER_T> inputs;
                    std::vector<AX_ENGINE_IO_BUFFER_T> outputs;
                    std::vector<char> model;

                    explicit Impl(const std::string& model_path) : model(read_binary(model_path)) {
                        check_ax(AX_SYS_Init(), "AX_SYS_Init failed");

                        AX_ENGINE_NPU_ATTR_T npu_attr;
                        std::memset(&npu_attr, 0, sizeof(npu_attr));
                        npu_attr.eHardMode = static_cast<AX_ENGINE_NPU_MODE_T>(0);
                        check_ax(AX_ENGINE_Init(&npu_attr), "AX_ENGINE_Init failed");

                        AX_ENGINE_HANDLE_EXTRA_T extra;
                        std::memset(&extra, 0, sizeof(extra));
                        char model_name[] = "mobilenet_v2";
                        extra.pName = reinterpret_cast<AX_S8*>(model_name);
                        check_ax(
                            AX_ENGINE_CreateHandleV2(
                                &handle, model.data(), static_cast<AX_U32>(model.size()), &extra),
                            "AX_ENGINE_CreateHandleV2 failed");
                        check_ax(AX_ENGINE_CreateContextV2(handle, &context), "AX_ENGINE_CreateContextV2 failed");
                        check_ax(AX_ENGINE_GetIOInfo(handle, &info), "AX_ENGINE_GetIOInfo failed");
                        if (!info || info->nInputSize < 1 || info->nOutputSize < 1) {
                            throw std::runtime_error("model has no input or output tensors");
                        }

                        inputs.resize(info->nInputSize);
                        outputs.resize(info->nOutputSize);
                        io.pInputs = inputs.data();
                        io.nInputSize = info->nInputSize;
                        io.pOutputs = outputs.data();
                        io.nOutputSize = info->nOutputSize;

                        for (AX_U32 i = 0; i < info->nInputSize; ++i) {
                            allocate(inputs[i], info->pInputs[i].nSize, "mobilenet_input");
                        }
                        for (AX_U32 i = 0; i < info->nOutputSize; ++i) {
                            allocate(outputs[i], info->pOutputs[i].nSize, "mobilenet_output");
                        }
                    }

                    ~Impl() {
                        for (auto& item : inputs) {
                            if (item.phyAddr) AX_SYS_MemFree(item.phyAddr, item.pVirAddr);
                        }
                        for (auto& item : outputs) {
                            if (item.phyAddr) AX_SYS_MemFree(item.phyAddr, item.pVirAddr);
                        }
                        if (handle) AX_ENGINE_DestroyHandle(handle);
                        AX_ENGINE_Deinit();
                        AX_SYS_Deinit();
                    }

                    static void allocate(AX_ENGINE_IO_BUFFER_T& buffer, AX_U32 size, const char* token) {
                        std::memset(&buffer, 0, sizeof(buffer));
                        buffer.nSize = size;
                        check_ax(
                            AX_SYS_MemAllocCached(
                                &buffer.phyAddr, &buffer.pVirAddr, buffer.nSize, 128,
                                reinterpret_cast<const AX_S8*>(token)),
                            "AX_SYS_MemAllocCached failed");
                    }
                };

                MobileNetRunner::MobileNetRunner(const std::string& model_path)
                    : impl_(new Impl(model_path)) {}

                MobileNetRunner::~MobileNetRunner() {
                    delete impl_;
                }

                std::vector<float> MobileNetRunner::run(const std::vector<float>& input) {
                    const auto input_bytes = input.size() * sizeof(float);
                    if (input_bytes > impl_->inputs[0].nSize) {
                        throw std::runtime_error("input tensor is larger than model input buffer");
                    }
                    std::memcpy(impl_->inputs[0].pVirAddr, input.data(), input_bytes);
                    AX_SYS_MflushCache(impl_->inputs[0].phyAddr, impl_->inputs[0].pVirAddr, impl_->inputs[0].nSize);
                    check_ax(AX_ENGINE_RunSyncV2(impl_->handle, impl_->context, &impl_->io), "AX_ENGINE_RunSyncV2 failed");
                    AX_SYS_MinvalidateCache(impl_->outputs[0].phyAddr, impl_->outputs[0].pVirAddr, impl_->outputs[0].nSize);

                    const auto output_count = impl_->outputs[0].nSize / sizeof(float);
                    std::vector<float> output(output_count);
                    std::memcpy(output.data(), impl_->outputs[0].pVirAddr, impl_->outputs[0].nSize);
                    return output;
                }

                std::vector<Classification> MobileNetRunner::classify(
                    const std::vector<float>& input,
                    const std::vector<std::string>& labels,
                    int k) {
                    auto logits = run(input);
                    std::vector<int> indices(logits.size());
                    std::iota(indices.begin(), indices.end(), 0);
                    const auto top_count = std::min<int>(k, static_cast<int>(indices.size()));
                    std::partial_sort(
                        indices.begin(), indices.begin() + top_count, indices.end(),
                        [&](int left, int right) { return logits[left] > logits[right]; });

                    std::vector<Classification> result;
                    for (int rank = 0; rank < top_count; ++rank) {
                        const int index = indices[rank];
                        const std::string label =
                            index < static_cast<int>(labels.size()) ? labels[index] : std::to_string(index);
                        result.push_back({rank + 1, index, logits[index], label});
                    }
                    return result;
                }

                std::vector<float> read_float_file(const std::string& path) {
                    auto bytes = read_binary(path);
                    if (bytes.size() % sizeof(float) != 0) {
                        throw std::runtime_error("input file size is not aligned to float32");
                    }
                    std::vector<float> values(bytes.size() / sizeof(float));
                    std::memcpy(values.data(), bytes.data(), bytes.size());
                    return values;
                }

                void write_float_file(const std::string& path, const std::vector<float>& values) {
                    std::ofstream file(path, std::ios::binary);
                    if (!file) {
                        throw std::runtime_error("failed to write " + path);
                    }
                    file.write(
                        reinterpret_cast<const char*>(values.data()),
                        static_cast<std::streamsize>(values.size() * sizeof(float)));
                }

                std::vector<std::string> read_labels(const std::string& path) {
                    std::ifstream file(path);
                    if (!file) {
                        throw std::runtime_error("failed to open labels file " + path);
                    }
                    std::vector<std::string> labels;
                    std::string line;
                    while (std::getline(file, line)) {
                        if (!line.empty()) {
                            labels.push_back(line);
                        }
                    }
                    return labels;
                }
                """
            ),
            encoding="utf-8",
        )
        (cpp_sdk / "examples" / "main.cpp").write_text(
            textwrap.dedent(
                """\
                #include "mobilenet_runner.hpp"

                #include <exception>
                #include <iostream>


                int main(int argc, char** argv) {
                    if (argc < 4 || argc > 6) {
                        std::cerr << "usage: " << argv[0]
                                  << " model.axmodel input.bin output.bin [labels.txt] [topk]\\n";
                        return 2;
                    }

                    try {
                        const std::string labels_path = argc >= 5 ? argv[4] : "imagenet_classes.txt";
                        const int topk = argc >= 6 ? std::stoi(argv[5]) : 5;
                        MobileNetRunner classifier(argv[1]);
                        const auto input = read_float_file(argv[2]);
                        const auto logits = classifier.run(input);
                        write_float_file(argv[3], logits);

                        const auto labels = read_labels(labels_path);
                        for (const auto& item : classifier.classify(input, labels, topk)) {
                            std::cout << item.rank << ": " << item.label
                                      << " (" << item.score << ")\\n";
                        }
                        return 0;
                    } catch (const std::exception& exc) {
                        std::cerr << exc.what() << "\\n";
                        return 1;
                    }
                }
                """
            ),
            encoding="utf-8",
        )
        (cpp_sdk / "imagenet_classes.txt").write_text(
            "\n".join(imagenet_labels) + "\n",
            encoding="utf-8",
        )
        (cpp_sdk / "README.md").write_text(
            textwrap.dedent(
                """\
                # C++ SDK

                该示例直接调用 AX runtime `libax_engine.so`/`libax_sys.so`，需要在主机交叉编译，
                再把二进制上传到板端运行。不要在板端编译。
                主要推理逻辑封装在 `MobileNetRunner` 类中；`examples/main.cpp` 只负责实例化
                该类并输出 ImageNet top-k 分类结果。

                ```bash
                cmake -S . -B build-aarch64 \\
                  -DCMAKE_TOOLCHAIN_FILE=toolchain-aarch64.cmake \\
                  -DAX_RUNTIME_ROOT=/path/to/ax/runtime
                cmake --build build-aarch64
                ```
                """
            ),
            encoding="utf-8",
        )
        (cpp_sdk / "toolchain-aarch64.cmake").write_text(
            textwrap.dedent(
                """\
                set(CMAKE_SYSTEM_NAME Linux)
                set(CMAKE_SYSTEM_PROCESSOR aarch64)
                set(CMAKE_C_COMPILER aarch64-none-linux-gnu-gcc)
                set(CMAKE_CXX_COMPILER aarch64-none-linux-gnu-g++)
                """
            ),
            encoding="utf-8",
        )

        run(["python", "-c", "import sys; sys.path.insert(0, 'sdk/python'); import mobilenet_sdk"], cwd=task_dir)
        run(["cmake", "-S", "sdk/cpp", "-B", "sdk/cpp/build"], cwd=task_dir, timeout=120)

        package = task_dir / "package"
        if package.exists():
            shutil.rmtree(package)
        for subdir in ["models", "python", "cpp", "model_convert", "reports"]:
            (package / subdir).mkdir(parents=True, exist_ok=True)
        shutil.copy2(task_dir / "compile" / "model.axmodel", package / "models" / "model.axmodel")
        shutil.copy2(task_dir / "export" / "model_meta.json", package / "models" / "model_meta.json")
        shutil.copytree(task_dir / "sdk" / "python", package / "python", dirs_exist_ok=True)
        shutil.copytree(
            task_dir / "sdk" / "cpp",
            package / "cpp",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("build", "build-*", "CMakeFiles"),
        )
        shutil.copy2(task_dir / "export" / "model.onnx", package / "model_convert" / "model.onnx")
        shutil.copy2(task_dir / "export" / "model_meta.json", package / "model_convert" / "model_meta.json")
        shutil.copy2(task_dir / "compile" / "pulsar2_config.json", package / "model_convert" / "pulsar2_config.json")
        shutil.copy2(task_dir / "export" / "export_report.md", package / "model_convert" / "export_report.md")
        (package / "model_convert" / "export_onnx.py").write_text(
            textwrap.dedent(
                """\
                import argparse
                import numpy as np
                import torch
                from torchvision.models import MobileNet_V2_Weights, mobilenet_v2


                def main():
                    parser = argparse.ArgumentParser()
                    parser.add_argument("--output", default="model.onnx")
                    args = parser.parse_args()

                    model = mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT).eval()
                    sample = torch.rand(1, 3, 224, 224, dtype=torch.float32)
                    np.save("sample_input.npy", sample.numpy().astype(np.float32))
                    torch.onnx.export(
                        model,
                        sample,
                        args.output,
                        input_names=["input"],
                        output_names=["logits"],
                        opset_version=17,
                        dynamo=False,
                    )


                if __name__ == "__main__":
                    main()
                """
            ),
            encoding="utf-8",
        )
        (package / "model_convert" / "compile_pulsar2.sh").write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail

                pulsar2 build --config pulsar2_config.json
                """
            ),
            encoding="utf-8",
        )
        (package / "model_convert" / "README.md").write_text(
            textwrap.dedent(
                f"""\
                # Model Convert

                This directory records how `models/model.axmodel` was produced.

                - `export_onnx.py`: exports MobileNetV2 from torchvision to static ONNX.
                - `model.onnx`: ONNX artifact used by Pulsar2.
                - `pulsar2_config.json`: Pulsar2 build configuration for `{TARGET_HARDWARE}`.
                - `compile_pulsar2.sh`: minimal build command when Pulsar2 is available on PATH.
                - `model_meta.json`: input/output metadata used by the SDKs.

                The original compile in this test used Docker image `{pulsar_image}` and explicitly
                kept `highest_mix_precision` disabled.
                """
            ),
            encoding="utf-8",
        )
        os.chmod(package / "model_convert" / "compile_pulsar2.sh", 0o755)
        for report in [
            task_dir / "export" / "export_report.md",
            task_dir / "compile" / "compile_report.md",
            task_dir / "simulate" / "simulate_report.md",
        ]:
            shutil.copy2(report, package / "reports" / report.name)
        shutil.copy2(task_dir / "task.md", package / "task.md")
        shutil.copy2(task_dir / "analysis.md", package / "analysis.md")
        (package / ".gitignore").write_text(
            textwrap.dedent(
                """\
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
                """
            ),
            encoding="utf-8",
        )
        (package / "README.md").write_text(
            textwrap.dedent(
                f"""\
                # MobileNetV2 AXMODEL Project

                - target: {TARGET_HARDWARE}
                - pulsar2_image: {pulsar_image}
                - cosine_similarity: {metrics['cosine_similarity']}

                This directory is a standalone customer project. It can be checked into git
                directly after removing or replacing any generated model artifacts your release
                policy does not want to version.

                ## Layout

                - `models/`: AXMODEL and model metadata.
                - `python/`: Python SDK and example using `pyaxengine`.
                - `cpp/`: C++ SDK/example using AX Engine runtime directly.
                - `model_convert/`: ONNX export script, Pulsar2 config, and conversion notes.
                - `reports/`: export, compile, simulate, and run-on-board reports.

                ## Python

                Dependencies are intentionally small: `numpy` and `pyaxengine`. The demo
                instantiates `MobileNetClassifier` and prints ImageNet top-k classes.

                ```bash
                LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/python \\
                  python3 python/mobilenet_sdk/example.py \\
                  --model models/model.axmodel --input input.npy --output python_output.npy
                ```

                ## C++

                Cross-compile on the host and run the binary on the AX board. The SDK
                exposes `MobileNetRunner`; `cpp/examples/main.cpp` is only a thin
                classification demo.

                ```bash
                cmake -S cpp -B cpp/build-aarch64 \\
                  -DCMAKE_TOOLCHAIN_FILE=cpp/toolchain-aarch64.cmake \\
                  -DAX_RUNTIME_ROOT=/path/to/ax/runtime
                cmake --build cpp/build-aarch64
                ```

                ## Model Conversion

                See `model_convert/README.md`, `model_convert/export_onnx.py`, and
                `model_convert/pulsar2_config.json` for the conversion recipe.
                """
            ),
            encoding="utf-8",
        )

    def _run_onboard(self, task_dir, sample):
        board = self._select_board(TARGET_HARDWARE)
        runonboard = task_dir / "runonboard"
        runonboard.mkdir(parents=True, exist_ok=True)

        input_npy = runonboard / "input.npy"
        input_bin = runonboard / "input.bin"
        np.save(input_npy, sample.astype(np.float32))
        sample.astype(np.float32).tofile(input_bin)

        runtime_root = self._fetch_ax_runtime(task_dir, board)
        cpp_binary = self._cross_compile_cpp_sdk(task_dir, runtime_root)

        remote_dir = f"/tmp/magnetar_mobilenet_{os.getpid()}"
        self._ssh(board, f"rm -rf {remote_dir} && mkdir -p {remote_dir}")
        self._scp_to(board, task_dir / "package", f"{remote_dir}/package")
        self._scp_to(board, input_npy, f"{remote_dir}/input.npy")
        self._scp_to(board, input_bin, f"{remote_dir}/input.bin")
        self._scp_to(board, cpp_binary, f"{remote_dir}/mobilenet_example")
        self._ssh(board, f"chmod +x {remote_dir}/mobilenet_example")

        if not self._board_has_pyaxengine(board):
            if not (PYAXENGINE_REPO / "axengine").is_dir():
                raise unittest.SkipTest("pyaxengine is not available on board or in /tmp/pyaxengine")
            self._scp_to(board, PYAXENGINE_REPO / "axengine", f"{remote_dir}/package/python/axengine")

        py_log = self._ssh(
            board,
            "cd {remote} && "
            "LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/package/python "
            "python3 package/python/mobilenet_sdk/example.py "
            "--model package/models/model.axmodel --input input.npy --output python_output.npy".format(
                remote=remote_dir
            ),
            timeout=240,
        )
        cpp_log = self._ssh(
            board,
            "cd {remote} && "
            "LD_LIBRARY_PATH=/soc/lib ./mobilenet_example "
            "package/models/model.axmodel input.bin cpp_output.bin "
            "package/cpp/imagenet_classes.txt".format(remote=remote_dir),
            timeout=240,
        )

        self._scp_from(board, f"{remote_dir}/python_output.npy", runonboard / "python_output.npy")
        self._scp_from(board, f"{remote_dir}/cpp_output.bin", runonboard / "cpp_output.bin")

        python_output = np.load(runonboard / "python_output.npy").astype(np.float32)
        cpp_output = np.fromfile(runonboard / "cpp_output.bin", dtype=np.float32).reshape(python_output.shape)
        metrics = {
            "board": board["host"],
            "chip_type": board["chip_type"],
            "target_hardware": TARGET_HARDWARE,
            "python_shape": list(python_output.shape),
            "cpp_shape": list(cpp_output.shape),
            "python_cpp_cosine": self._cosine(python_output, cpp_output),
            "python_cpp_mae": float(np.mean(np.abs(python_output - cpp_output))),
        }
        (runonboard / "runonboard_report.md").write_text(
            "# Run On Board Report\n\n"
            + "\n".join(f"- {key}: {value}" for key, value in metrics.items())
            + "\n\n## Python SDK Log\n\n```text\n"
            + py_log[-4000:]
            + "\n```\n\n## C++ SDK Log\n\n```text\n"
            + cpp_log[-4000:]
            + "\n```\n",
            encoding="utf-8",
        )
        shutil.copy2(
            runonboard / "runonboard_report.md",
            task_dir / "package" / "reports" / "runonboard_report.md",
        )
        with (task_dir / "task.md").open("a", encoding="utf-8") as f:
            f.write(f"\n- RUNONBOARD: {board['host']} {board['chip_type']}\n")
        return metrics

    def _select_board(self, target_hardware):
        explicit = os.environ.get("MAGNETAR_BOARD")
        if explicit:
            parsed = urllib.parse.urlparse(explicit if "://" in explicit else f"ssh://{explicit}")
            user = parsed.username or "root"
            host = parsed.hostname
            port = parsed.port or 22
            if not host:
                raise AssertionError(f"Invalid MAGNETAR_BOARD: {explicit}")
            chip_type = self._ssh(
                {"user": user, "host": host, "port": port, "password": BOARD_PASSWORD, "chip_type": ""},
                "cat /proc/ax_proc/chip_type 2>/dev/null || hostname",
                timeout=20,
            ).strip()
            if target_hardware.lower() not in chip_type.lower():
                raise AssertionError(
                    f"Board chip type {chip_type!r} does not match TARGET_HARDWARE={target_hardware}"
                )
            return {
                "user": user,
                "host": host,
                "port": port,
                "password": BOARD_PASSWORD,
                "chip_type": chip_type,
            }

        try:
            with urllib.request.urlopen(BOARD_DASHBOARD_URL, timeout=10) as response:
                payload = json.load(response)
        except Exception as exc:
            raise unittest.SkipTest(f"Board dashboard unavailable: {exc}") from exc

        devices = payload.get("devices", payload if isinstance(payload, list) else [])
        matches = []
        for item in devices:
            chip_type = str(item.get("chip_type", ""))
            if target_hardware.lower() not in chip_type.lower():
                continue
            if item.get("is_occupied"):
                continue
            host = item.get("ip") or item.get("host")
            if not host:
                continue
            matches.append(
                {
                    "user": item.get("default_user") or "root",
                    "host": host,
                    "port": int(item.get("ssh_port") or 22),
                    "password": BOARD_PASSWORD,
                    "chip_type": chip_type,
                }
            )
        if not matches:
            raise unittest.SkipTest(f"No free AX board matches TARGET_HARDWARE={target_hardware}")
        return matches[0]

    def _board_has_pyaxengine(self, board):
        proc = self._run_remote(
            board,
            "LD_LIBRARY_PATH=/soc/lib python3 - <<'PY'\n"
            "import axengine as axe\n"
            "providers = axe.get_available_providers()\n"
            "assert 'AxEngineExecutionProvider' in providers, providers\n"
            "PY",
            timeout=30,
        )
        return proc.returncode == 0

    def _fetch_ax_runtime(self, task_dir, board):
        runtime = task_dir / "cache" / "ax_runtime"
        if runtime.exists():
            shutil.rmtree(runtime)
        (runtime / "include").mkdir(parents=True, exist_ok=True)
        (runtime / "lib").mkdir(parents=True, exist_ok=True)
        self._scp_from(board, "/soc/include", runtime / "include_parent")
        include_parent = runtime / "include_parent"
        copied_include = include_parent / "include"
        if copied_include.is_dir():
            shutil.copytree(copied_include, runtime / "include", dirs_exist_ok=True)
            shutil.rmtree(include_parent)
        elif (include_parent / "ax_engine_api.h").is_file():
            shutil.copytree(include_parent, runtime / "include", dirs_exist_ok=True)
            shutil.rmtree(include_parent)
        self._scp_from(board, "/soc/lib/libax_engine.so", runtime / "lib" / "libax_engine.so")
        self._scp_from(board, "/soc/lib/libax_sys.so", runtime / "lib" / "libax_sys.so")
        return runtime

    def _cross_compile_cpp_sdk(self, task_dir, runtime_root):
        candidates = [
            os.environ.get("AARCH64_GXX"),
            shutil.which("aarch64-none-linux-gnu-g++"),
            "/usr/local/aarch64-none-linux-gnu-arm-9.2-2019.12/bin/aarch64-none-linux-gnu-g++",
        ]
        compiler = next((Path(item) for item in candidates if item and Path(item).exists()), None)
        if compiler is None:
            raise unittest.SkipTest("aarch64-none-linux-gnu-g++ is unavailable")
        output = task_dir / "sdk" / "cpp" / "build-aarch64" / "mobilenet_example"
        output.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                str(compiler),
                "-std=c++17",
                "-O2",
                "-I",
                str(task_dir / "sdk" / "cpp" / "include"),
                "-I",
                str(runtime_root / "include"),
                str(task_dir / "sdk" / "cpp" / "src" / "mobilenet_runner.cpp"),
                str(task_dir / "sdk" / "cpp" / "examples" / "main.cpp"),
                "-L",
                str(runtime_root / "lib"),
                "-Wl,-rpath,/soc/lib",
                "-Wl,--allow-shlib-undefined",
                "-lax_engine",
                "-lax_sys",
                "-o",
                str(output),
            ],
            timeout=180,
        )
        self.assertTrue(output.is_file())
        return output

    def _ssh_base(self, board):
        return [
            "sshpass",
            "-p",
            board["password"],
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-p",
            str(board["port"]),
            f"{board['user']}@{board['host']}",
        ]

    def _scp_base(self, board):
        return [
            "sshpass",
            "-p",
            board["password"],
            "scp",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-P",
            str(board["port"]),
        ]

    def _run_remote(self, board, command, timeout=120):
        return subprocess.run(
            self._ssh_base(board) + [command],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )

    def _ssh(self, board, command, timeout=120):
        proc = self._run_remote(board, command, timeout=timeout)
        if proc.returncode != 0:
            raise AssertionError(
                "remote command failed with exit code {}\n{}\n{}".format(
                    proc.returncode, command, proc.stdout
                )
            )
        return proc.stdout

    def _scp_to(self, board, source, dest):
        args = self._scp_base(board)
        if Path(source).is_dir():
            args.append("-r")
        run(args + [str(source), f"{board['user']}@{board['host']}:{dest}"], timeout=240)

    def _scp_from(self, board, source, dest):
        args = self._scp_base(board)
        if str(source).endswith("include"):
            args.append("-r")
        run(args + [f"{board['user']}@{board['host']}:{source}", str(dest)], timeout=240)

    def _assert_package_contract(self, task_dir):
        required = [
            "package/models/model.axmodel",
            "package/models/model_meta.json",
            "package/python/mobilenet_sdk/inference.py",
            "package/python/requirements.txt",
            "package/python/imagenet_classes.txt",
            "package/cpp/CMakeLists.txt",
            "package/cpp/include/mobilenet_runner.hpp",
            "package/cpp/src/mobilenet_runner.cpp",
            "package/cpp/examples/main.cpp",
            "package/cpp/imagenet_classes.txt",
            "package/model_convert/README.md",
            "package/model_convert/export_onnx.py",
            "package/model_convert/pulsar2_config.json",
            "package/model_convert/compile_pulsar2.sh",
            "package/reports",
            "package/reports/runonboard_report.md",
            "package/README.md",
            "package/.gitignore",
        ]
        for rel in required:
            path = task_dir / rel
            self.assertTrue(path.exists(), rel)
            if path.is_file():
                self.assertGreater(path.stat().st_size, 0, rel)

        meta = json.loads((task_dir / "package/models/model_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["model_name"], "mobilenet_v2")
        self.assertEqual(meta["inputs"][0]["shape"], [1, 3, 224, 224])
        self.assertEqual(meta["outputs"][0]["shape"], [1, 1000])
        readme = (task_dir / "package/README.md").read_text(encoding="utf-8")
        self.assertIn("standalone customer project", readme)
        self.assertIn("model_convert/pulsar2_config.json", readme)
        cpp_main = (task_dir / "package/cpp/examples/main.cpp").read_text(encoding="utf-8")
        self.assertTrue(cpp_main.startswith('#include "mobilenet_runner.hpp"'))
        self.assertIn("MobileNetRunner classifier", cpp_main)
        self.assertNotIn("ax_engine_api.h", cpp_main)
        self.assertFalse(cpp_main.startswith("\\"))
        cpp_runner = (task_dir / "package/cpp/include/mobilenet_runner.hpp").read_text(encoding="utf-8")
        self.assertIn("class MobileNetRunner", cpp_runner)
        py_inference = (task_dir / "package/python/mobilenet_sdk/inference.py").read_text(encoding="utf-8")
        self.assertIn("class MobileNetClassifier", py_inference)
        config = json.loads(
            (task_dir / "package/model_convert/pulsar2_config.json").read_text(encoding="utf-8")
        )
        self.assertFalse(config["quant"]["highest_mix_precision"])

    @staticmethod
    def _cosine(left, right):
        left = left.astype(np.float32).reshape(-1)
        right = right.astype(np.float32).reshape(-1)
        return float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right) + 1e-12))


if __name__ == "__main__":
    unittest.main()
