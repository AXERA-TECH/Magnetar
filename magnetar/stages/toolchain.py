"""TOOLCHAIN: 验证 Pulsar2 后端（独立包优先/docker 兜底）可用，并提取 proto 到本地缓存。"""
def run() -> str:
    from magnetar.docker_util import extract_pulsar2_proto, parse_backend, resolve_backend
    backend = resolve_backend()
    kind, name = parse_backend(backend)
    print(f"[TOOLCHAIN] Pulsar2 backend: {kind} ({name})")
    files = extract_pulsar2_proto(backend)
    print("[TOOLCHAIN] proto 已提取到本地缓存:")
    for name, path in files.items():
        print(f"  {name}: {path}")
    return backend
