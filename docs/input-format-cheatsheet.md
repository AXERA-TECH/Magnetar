# 输入/输出格式速查（成功案例固化）

> 目的：消除 Pulsar2 校准数据与 ax_run_model 输入格式的反复试错。
> 下列格式均来自仓库内已验证实现/成功案例 + 官方文档，按此执行，不要再试新格式。
>
> 本文件由 `python magnetar/pulsar2_ref.py --write-cheatsheet` 自动生成，请勿手改；
> 知识源在 `magnetar/io_format.py`（单一来源助手）与 `magnetar/pulsar2_ref.py`（成功案例）。

## TL;DR

| 场景 | 格式 | 依据 |
|------|------|------|
| Pulsar2 校准（通用 Numpy） | tar/tar.gz 内含 .npy（float32、带 batch 维、shape 与模型输入一致） | MobileNetV2 测试 / 通用导出器 |
| Pulsar2 校准（视觉 U8） | JPEG/PNG tar + mean/std=[0,0,0]/[255,255,255] + src_dtype=U8、src_layout=NHWC | YOLO（yolov8l_ylb.json 参考） |
| 多输入校准 | 每个输入独立 input_configs + tar.gz，tensor_name = ONNX 输入名 | PiperTTS |
| pulsar2 run 仿真 | 输入 {tensor名}.bin（float32 raw），输出 {输出名}.bin | 官方文档 + 测试 |
| ax_run_model 板端 | input_list.txt 每行一个 bin 文件名 + -m -i -o -l，输出 *.bin | 官方文档 + simulate.py |
| axengine SDK | np.ascontiguousarray(float32)，dtype 从 get_inputs()[0].dtype 读 | PiperTTS / MOSS-TTS |

## 1. Pulsar2 校准数据（量化输入）

- **校准样本优先真实业务数据**（真实输入或 ONNX 中间特征，如 PiperTTS 案例）；随机/扰动数据仅兜底——可能在标定集上好看，真实业务上崩
- 真实数据入口：`run_generic(calibration_data=<目录|样本列表>)` / `scripts/export_onnx.py --calib-dir`；未提供时导出器生成扰动序列，并在 `export_report.md` 标注 `perturbed 兜底`
- **COMPILE 前会自动预检校准集**（`magnetar/io_format.py::validate_calibration_archive`）：npy 的 shape/dtype/批维/数量不符会在编译前直接报错，不再等 Pulsar2 跑几分钟后才失败

### 1.1 通用单输入 FP32（MobileNetV2 / 通用导出器）

- 场景：非视觉或已在 CPU 侧归一化好的输入，Numpy 校准
- 数据：tar.gz 内含 {0000..NNNN}.npy，float32、带 batch 维、shape 与 input_shapes 完全一致
- 来源：magnetar/export_onnx.py + tests/test_magnetar_mobilenet_workflow.py（已跑通）

```json
{
  "quant": {
    "input_configs": [
      {
        "tensor_name": "<ONNX 输入名>",
        "calibration_dataset": "/workspace/export/calib_data/<输入名>.tar.gz",
        "calibration_format": "Numpy",
        "calibration_size": 30,
        "calibration_mean": [],
        "calibration_std": []
      }
    ],
    "calibration_method": "MinMax",
    "highest_mix_precision": false
  },
  "input_processors": [
    {
      "tensor_name": "<ONNX 输入名>",
      "tensor_layout": "NCHW",
      "src_dtype": "FP32",
      "src_layout": "NCHW"
    }
  ]
}
```

### 1.2 视觉 U8 输入（YOLO，参照 yolov8l_ylb.json）

- 场景：图像输入，预处理（归一化/布局转换）由工具链嵌入 axmodel
- 数据：JPEG/PNG 打包成 tar；工具链自动插 AxDequantizeLinear(U8→FP32) + AxNormalize + AxTranspose(NHWC→NCHW)
- 注意：calibration_std 必须是 255（非 0.004）；FP32 直通则 src_dtype=FP32、src_layout=NCHW、mean/std 显式 [0,0,0]/[1,1,1] 禁用归一化
- 来源：magnetar/stages/compile.py（input_dtype==U8 分支）+ issues/yolo_quantization_and_compile.md

```json
{
  "quant": {
    "input_configs": [
      {
        "tensor_name": "input",
        "calibration_dataset": "/workspace/export/calib_data/input.tar",
        "calibration_format": "Image",
        "calibration_size": 32,
        "calibration_mean": [
          0,
          0,
          0
        ],
        "calibration_std": [
          255,
          255,
          255
        ]
      }
    ],
    "calibration_method": "MinMax",
    "highest_mix_precision": false
  },
  "input_processors": [
    {
      "tensor_name": "input",
      "tensor_format": "RGB",
      "tensor_layout": "NHWC",
      "src_format": "RGB",
      "src_dtype": "U8",
      "src_layout": "NHWC"
    }
  ]
}
```

### 1.3 多输入校准（PiperTTS：z_p / mask）

- 场景：每个输入独立配置 input_configs + tar.gz
- 数据：跑原 ONNX 采集中间特征（sess.run 拿各输入），存 npy 后分别打包；校准集建议 4-32 个样本
- 来源：issues/piper_tts_experience.md §3（多输入余弦 0.987）

```json
{
  "quant": {
    "input_configs": [
      {
        "tensor_name": "z_p",
        "calibration_dataset": "/workspace/.../z_p.tar.gz",
        "calibration_format": "Numpy",
        "calibration_size": 8
      },
      {
        "tensor_name": "mask",
        "calibration_dataset": "/workspace/.../mask.tar.gz",
        "calibration_format": "Numpy",
        "calibration_size": 8
      }
    ],
    "calibration_method": "MinMax",
    "highest_mix_precision": false
  }
}
```

### 1.4 手写校准（MOSS-TTS-Realtime）

- 场景：手工构造校准集（非通用导出器）
- 数据：tar.gz 内 {input_name}/{index:05d}.npy 也可被接受（通用导出器用根目录 npy）；样本必须带 batch 维（如 [1,512,17]）；tensor_name 必须与 ONNX 输入名一致，校准文件名可不同
- 来源：issues/013_moss-tts-realtime_ax650_pipeline_pitfalls.md

```json
{
  "quant": {
    "input_configs": [
      {
        "tensor_name": "<ONNX 输入名>",
        "calibration_dataset": "/workspace/.../xxx.tar.gz",
        "calibration_format": "Numpy",
        "calibration_size": 16
      }
    ]
  }
}
```

## 2. pulsar2 run 仿真（SIMULATE 回退路径）

```bash
pulsar2 run --model /workspace/compile/model.axmodel \
  --input_dir /workspace/simulate/input --output_dir /workspace/simulate/output
```

- 输入：`simulate/input/{输入tensor名}.bin`（float32 raw）——**文件名必须与 tensor 名一致**
- 输出：`simulate/output/{输出tensor名}.bin`（float32 raw），按 ONNX 输出 shape reshape
- 代码：`magnetar/io_format.py::write_pulsar2_run_input / read_pulsar2_run_output`，调用点 `simulate.py::_run_pulsar2`
- 案例：`tests/test_magnetar_mobilenet_workflow.py::_simulate_and_compare`（验证通过）

## 3. ax_run_model 板端（SIMULATE 快速通道）

```bash
ax_run_model -m model.axmodel -i input_dir -o output -l input_dir/input_list.txt -w 0 -r 1
```

- `-w 0`：预热 0 次；`-r 1`：跑 1 次（仓库快速通道配置）
- 输入目录：`{输入tensor名}.bin`（float32 raw）+ `input_list.txt`（每行一个 bin 文件名）
- 输出：目录下 `*.bin`（float32 raw），单输出模型取第一个文件，reshape 成 ONNX 输出 shape
- 官方另一种目录结构（多输入/大批量时参考）：`input/0/data.bin` + `list.txt` 每行一个文件夹名，配合 `--use-tensor-name`
- 代码：`magnetar/io_format.py::write_ax_run_model_input / read_ax_run_model_output`，调用点 `simulate.py::_run_on_board`
- **上板前自动探测环境**（`magnetar/board_util.py::probe_board_env`）：ax_run_model 路径、pyaxengine、libax_engine 位置自动识别，缺依赖时报可执行提示，不再硬编码 `/opt/bin` 与 `/soc/lib`
- 注意：`Get model type failed`（issues/010）= 板端 ax 运行时与 Pulsar2 7.0 产物不兼容，换运行时/降版本，与输入格式无关

## 4. axengine SDK 板端输入

PiperTTS 成功用法：

```python
import axengine as axe
s = axe.InferenceSession("model.axmodel", providers=["AxEngineExecutionProvider"])
inputs = {s.get_inputs()[0].name: np.ascontiguousarray(data)}
out = s.run(None, inputs)[0]
```

- 输入必须 C-contiguous（`np.ascontiguousarray`）
- 用 `get_inputs()[0].name`，不要硬编码输入名
- MOSS-TTS（axengine 0.1.3）：无 `get_io_info`，dtype 从 `NodeArg.dtype` 读并强制转换

## 5. 常见错误对照表

| 现象 | 根因 | 正确姿势 |
|------|------|----------|
| 校准/板端输出全零 | calibration_std=0.004（即 1/255） | U8 用 [255,255,255] |
| 校准匹配不上 / 编译报 tensor 缺失 | tensor_name ≠ ONNX 输入名 | 用 `onnx inspect --io model.onnx` 核对 |
| Numpy 校准 shape 报错 | npy 少 batch 维或与 input_shapes 不一致 | 每个 npy 与输入 shape 完全一致 |
| pulsar2 run 无输出 | bin 文件名 ≠ tensor 名 | 文件名为 ONNX 输入/输出名 |
| 多输入只配了一个校准 | input_configs 缺项 | 每个输入独立配置 |
| 板端输出错位 | reshape 用错 shape | 用 ONNX 输出 shape（model_meta.json） |
| 板端 Get model type failed | ax 运行时与编译产物不兼容 | 换匹配的 ax 运行时 |
| 视觉模型精度差 | src_layout/src_dtype 与校准不一致 | U8+NHWC 或 FP32+NCHW 显式一致 |
| FP32 直通被偷偷归一化 | input_processors 没显式 mean/std | 显式 [0,0,0]/[1,1,1] |

## 权威依据

- Pulsar2 官方文档：
  - [Common configuration examples（校准格式/多输入/预处理嵌入）](https://pulsar2-docs.readthedocs.io/en/latest/appendix/advanced_config_examples.html)
  - [ax_run_model 模型评测工具](https://pulsar2-docs.readthedocs.io/zh-cn/latest/other_tools/ax_run_model.html)
- 仓库实现：`magnetar/export_onnx.py`、`magnetar/stages/compile.py`、`magnetar/stages/simulate.py`、`tests/`
- 经验记录：`issues/piper_tts_experience.md`、`issues/013_moss-tts-realtime_ax650_pipeline_pitfalls.md`、`issues/yolo_quantization_and_compile.md`
