"""TOOLCHAIN: 验证 Pulsar2 Docker 和 BSP 交叉编译器可用。"""
from pathlib import Path


def run() -> str:
    """返回可用的 pulsar2 Docker 镜像名称。"""
    from magnetar.docker_util import latest_pulsar2_image
    image = latest_pulsar2_image()
    print(f"[TOOLCHAIN] Pulsar2 image: {image}")
    return image
