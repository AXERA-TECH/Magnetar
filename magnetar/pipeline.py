"""Magnetar pipeline orchestrator — 串联 9 个阶段。"""
import os
import sys
from pathlib import Path

from magnetar.config import load_config
from magnetar.stages import init, acquire, export, toolchain, compile as _compile
from magnetar.stages import simulate, sdk_gen, runonboard, package as _package


def run_mobilenet() -> int:
    """完整 MobileNetV2 pipeline。返回 exit code。"""
    config = load_config()
    print(f"[Magnetar] TARGET_HARDWARE={config['TARGET_HARDWARE']}")
    print(f"[Magnetar] MODE={config['MODE']}")

    # ---- INIT ----
    print("\n=== INIT ===")
    task_dir = init.run(config)
    print(f"  TASK_DIR: {task_dir}")

    # ---- ACQUIRE ----
    print("\n=== ACQUIRE ===")
    source = config.get("SOURCE", "torchvision:mobilenet_v2")
    acquire.run(task_dir, source)
    print(f"  SOURCE: {source}")

    # ---- EXPORT ----
    print("\n=== EXPORT ===")
    sample = export.run_mobilenet(task_dir)
    print(f"  ONNX exported, sample shape: {sample.shape}")

    # ---- TOOLCHAIN ----
    print("\n=== TOOLCHAIN ===")
    pulsar_image = toolchain.run()
    print(f"  Pulsar2 image: {pulsar_image}")

    # ---- COMPILE ----
    print("\n=== COMPILE ===")
    _compile.run(task_dir, config["TARGET_HARDWARE"], pulsar_image)
    axmodel = task_dir / "compile" / "model.axmodel"
    print(f"  AXMODEL: {axmodel} ({axmodel.stat().st_size / 1024:.1f} KB)")

    # ---- SIMULATE ----
    print("\n=== SIMULATE ===")
    metrics = simulate.run(task_dir, sample, pulsar_image)
    print(f"  cosine_similarity: {metrics['cosine_similarity']:.6f}")
    if metrics["cosine_similarity"] < 0.98:
        print(f"  WARNING: cosine below 0.98 threshold")

    # ---- SDK-GEN ----
    print("\n=== SDK-GEN ===")
    from torchvision.models import MobileNet_V2_Weights
    labels = MobileNet_V2_Weights.DEFAULT.meta["categories"]
    sdk_gen.run_mobilenet_python(task_dir, labels)
    sdk_gen.run_mobilenet_cpp(task_dir, config["TARGET_HARDWARE"])
    print("  Python SDK + C++ SDK generated")

    # ---- RUNONBOARD ----
    print("\n=== RUNONBOARD ===")
    board_str = config.get("BOARD", "")
    if board_str:
        os.environ["MAGNETAR_BOARD"] = board_str
        board_metrics = runonboard.run(
            task_dir, sample, config["TARGET_HARDWARE"],
            config.get("BOARD_PASSWORD", "123456"))
        if board_metrics:
            print(f"  Board: {board_metrics.get('board')}")
            if "python_cpp_cosine" in board_metrics:
                print(f"  Python/C++ cosine: {board_metrics['python_cpp_cosine']:.6f}")
        else:
            print("  No board available, skipped")
    else:
        print("  BOARD not configured, skipped")

    # ---- PACKAGE ----
    print("\n=== PACKAGE ===")
    pkg = _package.assemble(task_dir, metrics, pulsar_image, labels=labels)
    print(f"  Package: {pkg}")

    print(f"\n[Magnetar] Pipeline complete. Output: {pkg}")
    return 0


def main():
    """CLI 入口。"""
    import os
    if len(sys.argv) > 1 and sys.argv[1] == "mobilenet":
        sys.exit(run_mobilenet())
    else:
        print("Usage: python -m magnetar.pipeline mobilenet")
        print()
        print("More model types coming soon.")
        sys.exit(1)


if __name__ == "__main__":
    main()
