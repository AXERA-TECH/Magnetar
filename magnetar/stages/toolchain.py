"""TOOLCHAIN: 验证 Pulsar2 Docker 可用，并把 proto 提取到本地缓存供工作流阅读。"""
def run() -> str:
    from magnetar.docker_util import latest_pulsar2_image
    img = latest_pulsar2_image()
    print(f"[TOOLCHAIN] Pulsar2 image: {img}")
    from magnetar.docker_util import extract_pulsar2_proto
    files = extract_pulsar2_proto(img)
    print("[TOOLCHAIN] proto 已提取到本地缓存:")
    for name, path in files.items():
        print(f"  {name}: {path}")
    return img
