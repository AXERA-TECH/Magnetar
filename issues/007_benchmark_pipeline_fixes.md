# [007] benchmark 全流程脚本踩坑合集（已全部修复进 run_one.sh）

记录 `todos/benchmark/run_one.sh` 打通 HF→ONNX→axmodel→SDK 全流程时修复的可复用问题。

## 7.1 HuggingFace 下载：代理导致 HEAD 请求失败
**现象**：`LocalEntryNotFoundError: cannot find the requested files`，但 `curl` 直连/代理均通。
**根因**：`hf-mirror.com` 直连即可；走 `http(s)_proxy=127.0.0.1:7890` 时 huggingface_hub 的
metadata HEAD 请求失败。
**修复**：HF 下载**不设** `http_proxy/https_proxy`；只有 github clone 才用 `git -c http.proxy=...`。
另需 `export HF_HUB_DISABLE_IMPLICIT_TOKEN=1`（新版 huggingface_hub 端点验证）。

## 7.2 transformers 间接 import torchaudio 失败
**现象**：`OSError: Could not load this library: .../_torchaudio.abi3.so`（CUDA 版本不匹配）。
**根因**：transformers 的 loss_rnnt 模块无条件 `import torchaudio`，而 miniforge 的 torchaudio
扩展与 torch 版本不匹配。
**修复**：import transformers 前 mock 掉 torchaudio。注意 MagicMock 不够，
transformers 用 `importlib.util.find_spec` 检测，需补 `__spec__` 和 `__version__`：
```python
import importlib.machinery
from unittest.mock import MagicMock
m = MagicMock()
m.__spec__ = importlib.machinery.ModuleSpec("torchaudio", loader=None)
m.__version__ = "0.0.0"
sys.modules['torchaudio'] = m
```

## 7.3 pulsar2 build：命令行参数缺 input_configs
**现象**：`NotImplementedError: Seems config of input(pixel_values) doesn't exist`。
**根因**：纯命令行 `--quant.input_sample_dir` 不会自动生成每个输入的 tensor_name 配置。
**修复**：改用 `--config pulsar2_config.json`，在 `quant.input_configs` 里显式写
`tensor_name` + `calibration_dataset`（tar 包）+ `calibration_format: Numpy`。

## 7.4 校准数据必须 float32（不是 uint8）
**根因**：CV 输入是归一化后 float32；给 uint8 会导致 dtype 校验失败或量化范围错误。
**修复**：`np.random.rand(*shape).astype(np.float32)`，打成 `calib.tar`。
（NLP 模型 int64 输入是另一回事，见 issue 002。）

## 7.5 pulsar2 run：输入 .bin 文件名必须是输入 tensor 名
**现象**：`pulsar2 run` 找不到输入 / 输出对不上。
**修复**：
- 输入：`--input_dir` 指向的目录里，bin 文件名须为 `<input_tensor_name>.bin`（如 `pixel_values.bin`），数据 float32 原始字节。
- 输出：写到 `--output_dir/<output_tensor_name>.bin`，用 `np.fromfile(..., dtype=np.float32)` 读回。

## 7.6 SDK-GEN heredoc 的 bad substitution
**现象**：`: bad substitution`。
**根因**：用 `$PY << PYEOF`（无引号）时 bash 会展开 C++ 模板里的 `${AXENGINE_ROOT}` 等。
**修复**：改 `<< 'PYEOF'`（quoted），需要的 shell 值通过 `KEY="$val" $PY << 'PYEOF'` 用
`os.environ` 传入，heredoc 内不再出现 `$shell_var`。

## 7.7 EVAL 误判 PASS / axengine 缺失误报
**修复**：
- status 按 cosine 阈值判定，不硬编码 PASS。
- 宿主机无 axengine 属正常 degrade，记 `ok_no_axengine`，只对真实语法错误记 fail（用 py_compile 区分）。

## 状态
以上全部已修复进 `todos/benchmark/run_one.sh`，hf_resnet50 全流程 0 STOP 跑通（cosine 0.9994）。
