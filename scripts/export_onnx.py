#!/usr/bin/env python3
"""Magnetar 通用 ONNX 导出 CLI（非 MobileNet 模型首选入口）。

用法示例：

  # 1) 已有模型对象不方便写脚本时，用 torchvision/timm/HF 架构名 + 权重
  python scripts/export_onnx.py --task-dir todos/work/demo \
      --arch torchvision:mobilenet_v2 --checkpoint weights.pt \
      --input-shapes 1x3x224x224 --model-name demo

  # 2) 最普适：提供 load 脚本（定义 build() 返回 (model, example_inputs)）
  python scripts/export_onnx.py --task-dir todos/work/demo \
      --load-script /path/to/load.py --model-name demo

  # 3) 多输入 / 显式命名
  python scripts/export_onnx.py --task-dir todos/work/demo \
      --load-script load.py \
      --input-names input ids --output-names logits \
      --opset 17 --calib-samples 8

成功后产物在 <task-dir>/export/：model.onnx、model_meta.json、
calib_data/<input_name>/*.npy + *.tar.gz、export_report.md。
失败时抛 ExportError，诊断报告写入 export/export_report.md。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from magnetar.export_onnx import export_to_onnx  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="通用 PyTorch -> 静态 ONNX 导出（先简后繁，自动降级）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--task-dir", required=True, help="TASK_DIR（export/ 会在其下创建）")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--load-script", help="用户脚本：定义 build() 返回 (model, example_inputs)")
    src.add_argument("--arch", help="torchvision:<name> | timm:<name> | hf:<repo>")
    parser.add_argument("--checkpoint", help="权重路径（配合 --arch，可选）")
    parser.add_argument("--input-shapes", help="示例输入形状，逗号分隔，如 1x3x224x224,1x2")
    parser.add_argument("--input-names", nargs="*", default=[], help="输入名（默认 input_0..）")
    parser.add_argument("--output-names", nargs="*", default=[], help="输出名（默认由 torch 自动命名）")
    parser.add_argument("--opset", type=int, default=17, help="首选 opset（失败自动降 13/11）")
    parser.add_argument("--model-name", default="model", help="写入 model_meta.json 的模型名")
    parser.add_argument("--calib-samples", type=int, default=4, help="校准样本数")
    parser.add_argument("--cosine-threshold", type=float, default=0.99, help="Torch-ONNX 对分阈值")
    args = parser.parse_args()

    kwargs: dict = dict(
        task_dir=args.task_dir,
        load_script=args.load_script,
        arch=args.arch,
        checkpoint=args.checkpoint,
        input_names=list(args.input_names) or None,
        output_names=list(args.output_names) or None,
        opset=args.opset,
        model_name=args.model_name,
        sample_variants=args.calib_samples,
        cosine_threshold=args.cosine_threshold,
    )
    if args.input_shapes:
        from magnetar.export_onnx import _example_inputs_from_shapes

        example_inputs, auto_names = _example_inputs_from_shapes(
            [s for s in args.input_shapes.split(",") if s.strip()]
        )
        kwargs["example_inputs"] = example_inputs
        kwargs.setdefault("input_names", auto_names)

    try:
        result = export_to_onnx(**kwargs)
    except Exception as exc:
        print(f"[export_onnx] 失败: {exc}", file=sys.stderr)
        return 1

    print(f"[export_onnx] OK: {result['onnx_path']}")
    print(f"[export_onnx] cosine={result['cosine']:.6f} "
          f"inputs={result['input_names']} outputs={result['output_names']}")
    print(f"[export_onnx] meta={Path(args.task_dir) / 'export' / 'model_meta.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
