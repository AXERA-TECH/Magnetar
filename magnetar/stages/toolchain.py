"""TOOLCHAIN: 验证 Pulsar2 Docker 可用。"""
def run() -> str:
    from magnetar.docker_util import latest_pulsar2_image
    img = latest_pulsar2_image()
    print(f"[TOOLCHAIN] Pulsar2 image: {img}")
    return img
