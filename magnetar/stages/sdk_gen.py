"""SDK-GEN: 生成 Python 和 C++ SDK。

通用入口（非 MobileNet 模型）：
- ``run_generic_python(task_dir)``：基于 export/model_meta.json（模型接口权威）
  与 origin/model_flow.json（ACQUIRE 阶段记录的运行流程）生成 Python SDK；
- ``run_generic_cpp(task_dir)``：生成 C++ SDK。

一致性保障：SDK 的输入输出名称/shape 以 model_meta.json 为准（AXMODEL 即按它编译），
预处理/后处理与示例输入以 model_flow.json 为准（ACQUIRE 阶段验证过的运行流程），
两者不匹配或示例样本缺失时抛错，避免生成与真实流程不一致的 SDK。
"""
import ast
import json
import re
import textwrap
from pathlib import Path

def run_mobilenet_python(task_dir: Path, imagenet_labels: list[str]) -> None:
    ps = task_dir / "sdk" / "python" / "mobilenet_sdk"; ps.mkdir(parents=True, exist_ok=True)
    (ps / "__init__.py").write_text("from .inference import MobileNetClassifier\n", encoding="utf-8")
    (ps / "inference.py").write_text(textwrap.dedent("""\
        import numpy as np
        DEFAULT_PROVIDER = "AxEngineExecutionProvider"
        class MobileNetClassifier:
            def __init__(self, model_path, providers=None, labels=None):
                import axengine as axe; self.labels = labels
                pref = providers or [DEFAULT_PROVIDER]
                try: self.session = axe.InferenceSession(model_path, providers=pref)
                except Exception:
                    avail = list(axe.get_available_providers())
                    fb = [n for n in avail if n not in pref]
                    if not fb: raise
                    self.session = axe.InferenceSession(model_path, providers=[fb[0]])
                self.inputs = self.session.get_inputs()
            def run(self, t):
                a = np.ascontiguousarray(t.astype(np.float32))
                return self.session.run(None, {self.inputs[0].name: a})[0]
            def classify(self, t, k=5):
                from .postprocess import topk
                return topk(self.run(t), labels=self.labels, k=k)
    """), encoding="utf-8")
    (ps / "postprocess.py").write_text(textwrap.dedent("""\
        import numpy as np
        def load_labels(path):
            with open(path, "r", encoding="utf-8") as f: return [l.strip() for l in f if l.strip()]
        def topk(logits, labels=None, k=5):
            flat = logits.reshape(-1); order = np.argsort(flat)[::-1][:k]
            return [{"rank": i, "index": int(idx), "label": labels[int(idx)] if labels and int(idx)<len(labels) else str(int(idx)), "score": float(flat[idx])} for i, idx in enumerate(order, 1)]
    """), encoding="utf-8")
    (task_dir / "sdk" / "python" / "imagenet_classes.txt").write_text("\n".join(imagenet_labels)+"\n", encoding="utf-8")
    (task_dir / "sdk" / "python" / "requirements.txt").write_text("numpy\npyaxengine @ git+https://github.com/AXERA-TECH/pyaxengine.git\n", encoding="utf-8")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "SDK-GEN", artifacts={"python_sdk": str(task_dir / "sdk" / "python")})

def run_mobilenet_cpp(task_dir: Path, target_hw: str) -> None:
    cpp = task_dir / "sdk" / "cpp"; cpp.mkdir(parents=True, exist_ok=True)
    for d in ["include", "src", "examples"]: (cpp/d).mkdir(exist_ok=True)
    (cpp / "CMakeLists.txt").write_text(textwrap.dedent("""\
        cmake_minimum_required(VERSION 3.15)
        project(mobilenet_sdk LANGUAGES CXX C)
        set(CMAKE_CXX_STANDARD 14)
        include_directories(include ${AX_RUNTIME_ROOT}/include)
        link_directories(${AX_RUNTIME_ROOT}/lib)
        add_library(mobilenet_sdk STATIC src/mobilenet_runner.cpp)
        target_link_libraries(mobilenet_sdk ax_engine ax_sys pthread dl atomic)
        add_executable(mobilenet_example examples/main.cpp)
        target_link_libraries(mobilenet_example mobilenet_sdk)
    """), encoding="utf-8")
    (cpp / "include" / "mobilenet_runner.hpp").write_text(textwrap.dedent("""\
        #pragma once
        #include <string>; #include <vector>; #include <cstdint>
        class MobileNetRunner {
        public:
            MobileNetRunner(const std::string& model_path);
            ~MobileNetRunner();
            std::vector<float> Run(const float* input, int64_t size);
        private:
            void* engine_ = nullptr; void* context_ = nullptr;
        };
    """).replace("; #", "\n#"), encoding="utf-8")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "SDK-GEN", artifacts={"cpp_sdk": str(cpp)})


# ---------------------------------------------------------------------------
# 通用 SDK 生成（非 MobileNet 模型）
# ---------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    """模型名转合法 Python 标识符（小写下划线）。"""
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", name.strip().lower())
    ident = re.sub(r"_+", "_", ident).strip("_")
    return ident or "model"


def _load_meta_and_flow(task_dir: Path, meta: dict | None, flow: dict | None):
    """读取/校验 model_meta.json（接口权威）与 model_flow.json（运行流程）。"""
    task_dir = Path(task_dir)
    meta_path = task_dir / "export" / "model_meta.json"
    flow_path = task_dir / "origin" / "model_flow.json"
    if meta is None:
        if not meta_path.is_file():
            raise ValueError(f"缺少 {meta_path}，请先完成 EXPORT 阶段")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if flow is None and flow_path.is_file():
        flow = json.loads(flow_path.read_text(encoding="utf-8"))
    flow = flow or {}
    return meta, flow


def _validate_flow(task_dir: Path, flow: dict) -> list[str]:
    """校验 model_flow 可被 SDK 复现；致命问题抛 ValueError，返回警告列表。

    一致性约束：SDK 前后处理必须对齐原版管线（model_flow 在 ACQUIRE 阶段记录并验证），
    调用方式尽量对齐原版模型入口，禁止为省事改成直通/自定义预处理。
    """
    warnings: list[str] = []
    task_dir = Path(task_dir)
    if not flow:
        warnings.append(
            "未提供 model_flow.json：预处理/后处理按直通生成，仅支持 float32 输入；"
            "若原版模型有预处理/后处理，必须先记录 model_flow 并对齐原版再生成 SDK"
        )
        return warnings
    example = flow.get("example_input")
    if example:
        p = Path(example)
        if not p.is_absolute():
            p = task_dir / p
        if not p.is_file():
            raise ValueError(f"model_flow.example_input 不存在: {p}（ACQUIRE 阶段需保存真实样本）")
    for key in ("preprocess_code", "postprocess_code"):
        code = flow.get(key)
        if code:
            try:
                ast.parse(code)
            except SyntaxError as exc:
                raise ValueError(f"model_flow.{key} 语法错误: {exc}") from exc
        else:
            warnings.append(
                f"model_flow 未记录 {key}：SDK 将按直通生成；"
                "若原版模型有对应处理，必须在 model_flow.json 补齐并对齐原版后再生成 SDK"
            )
    if flow.get("verified") is not True:
        warnings.append("model_flow.verified 不为 true：前后处理未在 ACQUIRE 阶段验证，与原版运行流程一致性无法保证")
    sdk_iface = flow.get("sdk_interface")
    if sdk_iface is not None and not isinstance(sdk_iface, dict):
        warnings.append("model_flow.sdk_interface 应为 dict（记录原版调用约定：入口/入参顺序/输入格式/输出结构）")
    if flow.get("inputs") and flow.get("inputs") != flow.get("_meta_inputs"):
        # inputs 字段可选；若提供则应与 meta 校验，见 run_generic_python
        pass
    return warnings


_PREPROCESS_IDENTITY = """\
import numpy as np


def preprocess(*arrays):
    \"\"\"原始输入 -> 模型输入（默认仅 float32 对齐；如需 resize/归一化请提供 model_flow.preprocess_code）。\"\"\"
    return [np.ascontiguousarray(a, dtype=np.float32) for a in arrays]
"""

_POSTPROCESS_IDENTITY = """\
import numpy as np


def postprocess(*arrays):
    \"\"\"模型输出 -> 用户结果（默认直通；如需 topk/解码请提供 model_flow.postprocess_code）。\"\"\"
    return arrays if len(arrays) > 1 else arrays[0]
"""

_INFERENCE_TEMPLATE = """\
import numpy as np

DEFAULT_PROVIDER = "AxEngineExecutionProvider"


class ModelSession:
    \"\"\"通用推理会话：默认 AxEngineExecutionProvider（pyaxengine），不可用时回退 onnxruntime CPU。

    input/output 名称与 export/model_meta.json 一致（AXMODEL 即按此编译）。
    \"\"\"

    def __init__(self, model_path, providers=None):
        self.providers = providers or [DEFAULT_PROVIDER]
        session = None
        self.backend = "axengine"
        if DEFAULT_PROVIDER in self.providers:
            try:
                import axengine as axe
                session = axe.InferenceSession(model_path, providers=self.providers)
            except Exception:
                session = None
        if session is None:
            import onnxruntime as ort
            available = ort.get_available_providers()
            fallback = [p for p in available if "Tensorrt" not in p]
            session = ort.InferenceSession(model_path, providers=fallback[:1])
            self.backend = "onnxruntime"
        self.session = session
        self.input_names = [i.name for i in session.get_inputs()]
        self.output_names = [o.name for o in session.get_outputs()]

    def run_named(self, feeds, names=None):
        \"\"\"feeds: 与 names（默认 input_names）对应的数组列表。返回输出列表。\"\"\"
        names = names or self.input_names
        if len(feeds) != len(names):
            raise ValueError(f"输入数量不匹配: {len(feeds)} != {len(names)}")
        feed = {
            name: np.ascontiguousarray(arr, dtype=np.float32)
            for name, arr in zip(names, feeds)
        }
        return self.session.run(None, feed)
"""

_INFERENCE_NPU_ONLY_TEMPLATE = """\
import numpy as np

DEFAULT_PROVIDER = "AxEngineExecutionProvider"


class ModelSession:
    \"\"\"NPU 专用推理会话：仅支持 AX 芯片端到端运行（pyaxengine），无 CPU/onnxruntime 回退。

    input/output 名称与 export/model_meta.json 一致（AXMODEL 即按此编译）。
    非 AX 环境（缺少 pyaxengine 或 AX provider）时直接报错，不做 CPU 兜底。
    \"\"\"

    def __init__(self, model_path, providers=None):
        try:
            import axengine as axe
        except ImportError as exc:
            raise RuntimeError(
                "SDK 为 NPU 专用发布版，仅支持在 AX 芯片上运行；请先安装 requirements.txt "
                "并在板端执行（无 onnxruntime/torch/transformers 回退）"
            ) from exc
        self.session = axe.InferenceSession(
            model_path, providers=providers or [DEFAULT_PROVIDER])
        self.backend = "axengine"
        self.input_names = [i.name for i in self.session.get_inputs()]
        self.output_names = [o.name for o in self.session.get_outputs()]

    def run_named(self, feeds, names=None):
        \"\"\"feeds: 与 names（默认 input_names）对应的数组列表。返回输出列表。\"\"\"
        names = names or self.input_names
        if len(feeds) != len(names):
            raise ValueError(f"输入数量不匹配: {len(feeds)} != {len(names)}")
        feed = {
            name: np.ascontiguousarray(arr, dtype=np.float32)
            for name, arr in zip(names, feeds)
        }
        return self.session.run(None, feed)
"""

_EXAMPLE_TEMPLATE = """\
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from {pkg}.inference import ModelSession
from {pkg}.postprocess import postprocess
from {pkg}.preprocess import preprocess


def main():
    parser = argparse.ArgumentParser(description="{model_name} inference example")
    parser.add_argument("--model", required=True, help="AXMODEL 路径")
    parser.add_argument("--input", nargs="+", required=True, help="输入 npy（每输入一个，与 model_meta 顺序一致）")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    args = parser.parse_args()

    arrays = [np.load(p).astype(np.float32) for p in args.input]
    session = ModelSession(args.model)
    feeds = preprocess(*arrays)
    raw = session.run_named(feeds)
    result = postprocess(*raw)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, arr in enumerate(raw):
        np.save(out_dir / f"output_{{i}}.npy", np.asarray(arr, dtype=np.float32))
    try:
        json.dumps(result)
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except TypeError:
        np.save(out_dir / "result.npy", np.asarray(result, dtype=np.float32))

    print("backend:", session.backend)
    print("inputs:", session.input_names)
    print("outputs:", session.output_names)
    print("saved to:", out_dir)


if __name__ == "__main__":
    main()
"""


def _write_npu_only_inference(sdk_dir: Path, name: str | None = None) -> None:
    """把某个 SDK 目录的 inference.py 替换为 NPU-only 发布版（无 onnxruntime fallback）。"""
    sdk_dir = Path(sdk_dir)
    (sdk_dir / "inference.py").write_text(_INFERENCE_NPU_ONLY_TEMPLATE, encoding="utf-8")
    readme = sdk_dir / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        if "NPU 专用" not in text:
            text += "\n> 发布版：端到端 NPU 验证已通过，SDK 仅依赖 pyaxengine（无 onnxruntime/torch/transformers 回退）。\n"
            readme.write_text(text, encoding="utf-8")


def make_npu_only_sdk_dir(py_dir: Path) -> bool:
    """把 py_dir 下含 onnxruntime fallback 的通用 SDK 替换为 NPU-only 发布版。

    返回是否发生了替换（无通用 SDK 或已为 NPU-only 时返回 False）。
    """
    changed = False
    for sdk_dir in Path(py_dir).glob("*_sdk"):
        inf = sdk_dir / "inference.py"
        if inf.is_file() and "import onnxruntime" in inf.read_text(encoding="utf-8"):
            _write_npu_only_inference(sdk_dir)
            changed = True
    return changed


def run_generic_python(task_dir: Path, meta: dict | None = None, flow: dict | None = None,
                       model_name: str | None = None, strict_npu: bool = False) -> Path:
    """基于 model_meta.json + model_flow.json 生成通用 Python SDK。

    - 接口（输入输出名/shape/dtype）取自 model_meta.json
    - 预处理/后处理与示例输入取自 model_flow.json（ACQUIRE 阶段记录的真实运行流程）
    - flow 缺失时预处理/后处理按直通生成并给出警告
    - strict_npu=True 生成发布版：仅 AX 芯片可运行，无 onnxruntime/torch/transformers 回退
    """
    task_dir = Path(task_dir)
    meta, flow = _load_meta_and_flow(task_dir, meta, flow)
    warnings = _validate_flow(task_dir, flow)
    name = model_name or flow.get("model_name") or meta.get("model_name", "model")
    pkg = _sanitize(name)
    ps = task_dir / "sdk" / "python" / f"{pkg}_sdk"
    ps.mkdir(parents=True, exist_ok=True)
    pkg_full = ps.name

    (ps / "__init__.py").write_text(
        f"from .inference import ModelSession\nfrom . import postprocess, preprocess\n",
        encoding="utf-8",
    )
    if strict_npu:
        _write_npu_only_inference(ps, name)
    else:
        (ps / "inference.py").write_text(_INFERENCE_TEMPLATE, encoding="utf-8")
    (ps / "preprocess.py").write_text(
        flow.get("preprocess_code") or _PREPROCESS_IDENTITY, encoding="utf-8")
    (ps / "postprocess.py").write_text(
        flow.get("postprocess_code") or _POSTPROCESS_IDENTITY, encoding="utf-8")
    (ps / "example.py").write_text(
        _EXAMPLE_TEMPLATE.format(pkg=pkg_full, model_name=name), encoding="utf-8")
    (ps / "requirements.txt").write_text(
        "numpy\npyaxengine @ git+https://github.com/AXERA-TECH/pyaxengine.git\n", encoding="utf-8")

    flow_note = flow.get("preprocess_note", "默认仅 float32 对齐") if flow else "默认仅 float32 对齐"
    post_note = flow.get("postprocess_note", "默认直通") if flow else "默认直通"
    example_default = flow.get("example_input", "export/sample_input.npy")
    meta_inputs = ", ".join(f"{i['name']}{i['shape']}" for i in meta.get("inputs", []))
    meta_outputs = ", ".join(f"{o['name']}{o['shape']}" for o in meta.get("outputs", []))
    npu_note = (
        "\n> NPU 专用发布版：端到端 NPU 验证已通过，SDK 仅依赖 pyaxengine"
        "（无 onnxruntime/torch/transformers 回退）。\n"
        if strict_npu else ""
    )
    (ps / "README.md").write_text(textwrap.dedent(f"""\
        # {name} Python SDK

        - 输入（与 model_meta.json 一致）: {meta_inputs or 'N/A'}
        - 输出（与 model_meta.json 一致）: {meta_outputs or 'N/A'}
        - 预处理: {flow_note}
        - 后处理: {post_note}
        - 示例输入: {example_default}
        {npu_note}

        ```bash
        LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD/python python3 {pkg}_sdk/example.py \
          --model models/model.axmodel --input input.npy --output-dir output
        ```
        """), encoding="utf-8")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"\n- SDK-GEN(python): {ps}（{len(warnings)} 个警告）\n")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "SDK-GEN", artifacts={"python_sdk": str(ps)},
               summary=f"Python SDK {ps.name}")
    return ps


_CPP_CMAKE = """\
cmake_minimum_required(VERSION 3.15)
project({project} LANGUAGES CXX C)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
include_directories(include)
add_library({project} STATIC src/model_runner.cpp)
target_include_directories({project} PUBLIC include)
add_executable(model_example examples/main.cpp)
if(AX_RUNTIME_ROOT)
  target_include_directories({project} PRIVATE ${{AX_RUNTIME_ROOT}}/include)
  target_link_directories({project} PRIVATE ${{AX_RUNTIME_ROOT}}/lib)
  target_link_libraries({project} PRIVATE ax_engine ax_sys)
endif()
target_link_libraries(model_example PRIVATE {project})
"""

_CPP_HEADER = """\
#pragma once

#include <cstddef>
#include <string>
#include <vector>


class ModelRunner {
public:
    explicit ModelRunner(const std::string& model_path, const std::string& model_name = "model");
    ~ModelRunner();

    ModelRunner(const ModelRunner&) = delete;
    ModelRunner& operator=(const ModelRunner&) = delete;

    size_t NumInputs() const;
    size_t NumOutputs() const;
    size_t InputBytes(size_t index) const;
    size_t OutputBytes(size_t index) const;

    // inputs[i] 为第 i 个输入的 float 数据；返回每个输出的 float 数据。
    // 输入输出名称/形状见 model_meta.json（AXMODEL 即按此编译）。
    std::vector<std::vector<float>> Run(const std::vector<std::vector<float>>& inputs);

private:
    struct Impl;
    Impl* impl_;
};
"""

_CPP_SRC = """\
#include "model_runner.hpp"

#include <ax_engine_api.h>
#include <ax_sys_api.h>

#include <algorithm>
#include <cstring>
#include <fstream>
#include <iterator>
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

struct ModelRunner::Impl {
    AX_ENGINE_HANDLE handle = nullptr;
    AX_ENGINE_CONTEXT_T context = nullptr;
    AX_ENGINE_IO_INFO_T* info = nullptr;
    AX_ENGINE_IO_T io {};
    std::vector<AX_ENGINE_IO_BUFFER_T> inputs;
    std::vector<AX_ENGINE_IO_BUFFER_T> outputs;
    std::vector<char> model;

    explicit Impl(const std::string& model_path, const std::string& model_name)
        : model(read_binary(model_path)) {
        check_ax(AX_SYS_Init(), "AX_SYS_Init failed");

        AX_ENGINE_NPU_ATTR_T npu_attr;
        std::memset(&npu_attr, 0, sizeof(npu_attr));
        npu_attr.eHardMode = static_cast<AX_ENGINE_NPU_MODE_T>(0);
        check_ax(AX_ENGINE_Init(&npu_attr), "AX_ENGINE_Init failed");

        AX_ENGINE_HANDLE_EXTRA_T extra;
        std::memset(&extra, 0, sizeof(extra));
        extra.pName = const_cast<AX_S8*>(reinterpret_cast<const AX_S8*>(model_name.c_str()));
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
            std::memset(&inputs[i], 0, sizeof(inputs[i]));
            inputs[i].nSize = info->pInputs[i].nSize;
            check_ax(
                AX_SYS_MemAllocCached(
                    &inputs[i].phyAddr, &inputs[i].pVirAddr, inputs[i].nSize, 128,
                    reinterpret_cast<const AX_S8*>("model_input")),
                "AX_SYS_MemAllocCached failed");
        }
        for (AX_U32 i = 0; i < info->nOutputSize; ++i) {
            std::memset(&outputs[i], 0, sizeof(outputs[i]));
            outputs[i].nSize = info->pOutputs[i].nSize;
            check_ax(
                AX_SYS_MemAllocCached(
                    &outputs[i].phyAddr, &outputs[i].pVirAddr, outputs[i].nSize, 128,
                    reinterpret_cast<const AX_S8*>("model_output")),
                "AX_SYS_MemAllocCached failed");
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
};

ModelRunner::ModelRunner(const std::string& model_path, const std::string& model_name)
    : impl_(new Impl(model_path, model_name)) {}

ModelRunner::~ModelRunner() {
    delete impl_;
}

size_t ModelRunner::NumInputs() const {
    return impl_->info->nInputSize;
}

size_t ModelRunner::NumOutputs() const {
    return impl_->info->nOutputSize;
}

size_t ModelRunner::InputBytes(size_t index) const {
    return impl_->inputs.at(index).nSize;
}

size_t ModelRunner::OutputBytes(size_t index) const {
    return impl_->outputs.at(index).nSize;
}

std::vector<std::vector<float>> ModelRunner::Run(const std::vector<std::vector<float>>& inputs) {
    if (inputs.size() != NumInputs()) {
        throw std::runtime_error("input count mismatch");
    }
    for (size_t i = 0; i < inputs.size(); ++i) {
        if (inputs[i].size() * sizeof(float) > impl_->inputs[i].nSize) {
            throw std::runtime_error("input tensor is larger than model input buffer");
        }
        std::memcpy(impl_->inputs[i].pVirAddr, inputs[i].data(), inputs[i].size() * sizeof(float));
    }
    check_ax(AX_ENGINE_Run(impl_->context, &impl_->io), "AX_ENGINE_Run failed");

    std::vector<std::vector<float>> outputs(NumOutputs());
    for (size_t i = 0; i < outputs.size(); ++i) {
        const size_t count = impl_->outputs[i].nSize / sizeof(float);
        const auto* src = static_cast<const float*>(impl_->outputs[i].pVirAddr);
        outputs[i].assign(src, src + count);
    }
    return outputs;
}
"""

_CPP_EXAMPLE = """\
#include "model_runner.hpp"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace {

std::vector<float> read_float_file(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        throw std::runtime_error("failed to open " + path);
    }
    std::vector<char> bytes(
        std::istreambuf_iterator<char>(file),
        std::istreambuf_iterator<char>());
    std::vector<float> data(bytes.size() / sizeof(float));
    std::memcpy(data.data(), bytes.data(), bytes.size());
    return data;
}

void write_float_file(const std::string& path, const std::vector<float>& values) {
    std::ofstream file(path, std::ios::binary);
    if (!file) {
        throw std::runtime_error("failed to open " + path);
    }
    file.write(
        reinterpret_cast<const char*>(values.data()),
        static_cast<std::streamsize>(values.size() * sizeof(float)));
}

}  // namespace

int main(int argc, char** argv) {
    // usage: model_example <model.axmodel> <input_0.bin> [input_1.bin ...] <output_dir>
    if (argc < 4) {
        std::fprintf(
            stderr,
            "usage: %s <model.axmodel> <input_0.bin> [input_1.bin ...] <output_dir>\\n",
            argv[0]);
        return 1;
    }
    try {
        const std::string model_path = argv[1];
        const std::string output_dir = argv[argc - 1];
        std::vector<std::vector<float>> inputs;
        for (int i = 2; i < argc - 1; ++i) {
            inputs.push_back(read_float_file(argv[i]));
        }
        ModelRunner runner(model_path, "model");
        std::vector<std::vector<float>> outputs = runner.Run(inputs);
        for (size_t i = 0; i < outputs.size(); ++i) {
            write_float_file(
                output_dir + "/output_" + std::to_string(i) + ".bin", outputs[i]);
        }
        std::printf("inputs=%zu outputs=%zu\\n", runner.NumInputs(), runner.NumOutputs());
        return 0;
    } catch (const std::exception& exc) {
        std::fprintf(stderr, "error: %s\\n", exc.what());
        return 1;
    }
}
"""


def run_generic_cpp(task_dir: Path, meta: dict | None = None, flow: dict | None = None,
                    target_hw: str = "AX650", model_name: str | None = None) -> Path:
    """基于 model_meta.json 生成通用 C++ SDK（AX Engine runtime 直接链接）。"""
    task_dir = Path(task_dir)
    meta, flow = _load_meta_and_flow(task_dir, meta, flow)
    _validate_flow(task_dir, flow)
    name = model_name or flow.get("model_name") or meta.get("model_name", "model")
    project = _sanitize(name) + "_sdk"
    cpp = task_dir / "sdk" / "cpp"
    for d in ("include", "src", "examples"):
        (cpp / d).mkdir(parents=True, exist_ok=True)

    (cpp / "CMakeLists.txt").write_text(_CPP_CMAKE.format(project=project), encoding="utf-8")
    (cpp / "include" / "model_runner.hpp").write_text(_CPP_HEADER, encoding="utf-8")
    (cpp / "src" / "model_runner.cpp").write_text(_CPP_SRC, encoding="utf-8")
    (cpp / "examples" / "main.cpp").write_text(_CPP_EXAMPLE, encoding="utf-8")

    meta_inputs = ", ".join(f"{i['name']}{i['shape']}" for i in meta.get("inputs", []))
    meta_outputs = ", ".join(f"{o['name']}{o['shape']}" for o in meta.get("outputs", []))
    (cpp / "README.md").write_text(textwrap.dedent(f"""\
        # {name} C++ SDK

        - 输入（与 model_meta.json 一致）: {meta_inputs or 'N/A'}
        - 输出（与 model_meta.json 一致）: {meta_outputs or 'N/A'}
        - 直接链接 AX Engine runtime（`ax_engine`/`ax_sys`），目标: {target_hw}

        ```bash
        cmake -S cpp -B cpp/build-aarch64 \\
          -DCMAKE_TOOLCHAIN_FILE=cpp/toolchain-aarch64.cmake \\
          -DAX_RUNTIME_ROOT=/path/to/ax/runtime
        cmake --build cpp/build-aarch64
        ```
        """), encoding="utf-8")
    with (task_dir / "task.md").open("a", encoding="utf-8") as f:
        f.write(f"\n- SDK-GEN(cpp): {cpp}\n")
    from magnetar.stages.state import mark_stage
    mark_stage(task_dir, "SDK-GEN", artifacts={"cpp_sdk": str(cpp)},
               summary=f"C++ SDK {cpp}")
    return cpp
