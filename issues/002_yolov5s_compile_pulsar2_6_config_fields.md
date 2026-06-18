# Issue 002: yolov5s COMPILE Pulsar2 6.0 配置字段差异

## 问题描述

使用 `pulsar2:6.0` 编译 YOLOv5s 静态 ONNX 时，初始配置因字段不匹配和校准入口配置不完整失败。

## 环境信息

- 模型: YOLOv5s
- Pulsar2: `6.0`
- commit: `48520c11`
- 目标芯片: `AX650`
- NPU mode: `NPU1`

## 复现步骤

1. 准备静态 ONNX，输入 `images: [1,3,640,640]` FP32 NCHW。
2. 使用包含 `dst_format` / `dst_layout` 的 `input_processors`。
3. 或只配置 `quant.input_sample_dir`，不配置 `quant.input_configs`。
4. 执行 `pulsar2 build --config pulsar2_config.json`。

## 关键日志

```text
Message type "pulsar2.build.InputProcessor" has no field named "dst_format"
```

```text
NotImplementedError: Seems config of input(images) doesn't exist
```

```text
FileNotFoundError: Could not find file `images' in `calib_data'
```

## 根本原因

Pulsar2 6.0 的 `InputProcessor` protobuf 字段为 `tensor_format` / `tensor_layout` / `src_format` / `src_layout` / `src_dtype`，不支持 `dst_format` / `dst_layout`。

量化校准入口需要 `quant.input_configs`，其中包含 `tensor_name`、`calibration_dataset`、`calibration_format`、`calibration_size`。`quant.input_sample_dir` 用于精度分析/样本读取，不等价于校准数据配置。

## 解决方案

使用如下配置形态：

```json
{
  "quant": {
    "input_configs": [
      {
        "tensor_name": "images",
        "calibration_dataset": "calib_data/images.tar.gz",
        "calibration_format": "Numpy",
        "calibration_size": -1,
        "calibration_mean": [],
        "calibration_std": []
      }
    ]
  },
  "input_processors": [
    {
      "tensor_name": "images",
      "tensor_format": "RGB",
      "tensor_layout": "NCHW",
      "src_format": "RGB",
      "src_dtype": "FP32",
      "src_layout": "NCHW"
    }
  ]
}
```

如不做编译阶段精度分析，不要配置 `quant.input_sample_dir` / `compiler.input_sample_dir`。

## 经验教训

遇到 Pulsar2 配置字段问题时，优先读取镜像内 `/opt/pulsar2/yamain/config/build_config.proto`，以当前版本 protobuf 为准。

## 相关产物

- `todos/work/20260618-190157-yolov5s/compile/pulsar2_config.json`
- `todos/work/20260618-190157-yolov5s/compile/build.log`
