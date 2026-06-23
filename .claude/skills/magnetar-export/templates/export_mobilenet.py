#!/usr/bin/env python3
"""MobileNet ONNX 导出示例脚本"""
import argparse
import torch
import numpy as np
from pathlib import Path

# 依赖检查
try:
    import onnxscript
except ImportError:
    print("错误: 缺少 onnxscript 依赖")
    print("安装命令: python3 -m pip install onnxscript")
    exit(1)

def export_onnx(model_name='mobilenet_v2', output_dir='cache'):
    """导出 MobileNet 到 ONNX"""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # 加载预训练模型
    model = torch.hub.load('pytorch/vision:v0.10.0', model_name, pretrained=True)
    model.eval()

    # 准备输入
    dummy_input = torch.randn(1, 3, 224, 224)

    # 导出 ONNX
    onnx_path = output_dir / f"{model_name}.onnx"
    torch.onnx.export(
        model, dummy_input, str(onnx_path),
        input_names=['input'], output_names=['output'],
        opset_version=11, dynamo=False
    )
    print(f"✓ ONNX 模型已导出: {onnx_path}")

    # 生成校准数据
    calib_dir = output_dir / 'calib_data' / 'input'
    calib_dir.mkdir(parents=True, exist_ok=True)

    for i in range(10):
        data = np.random.randn(1, 3, 224, 224).astype(np.float32)
        np.save(calib_dir / f'data_{i:03d}.npy', data)
    print(f"✓ 校准数据已生成: {calib_dir}")

    return onnx_path

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='mobilenet_v2', help='模型名称')
    parser.add_argument('--output', default='cache', help='输出目录')
    args = parser.parse_args()

    export_onnx(args.model, args.output)
