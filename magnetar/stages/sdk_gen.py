"""SDK-GEN: 生成 Python 和 C++ SDK。"""
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
