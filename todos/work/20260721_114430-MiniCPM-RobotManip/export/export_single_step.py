"""
导出 MiniCPM-VLA Action Head 单步 _predict 到静态 ONNX。

策略：
- 只导出 _predict 一步，4 步去噪循环放 Python SDK
- 输入: noisy_actions(1,30,80) + vl_embs(1,80,1024) + state(1,80) + timestep(1,) + embodiment_id(1,)
- 输出: denoised_actions(1,30,80)
- 图规模缩小约 4 倍
"""
import sys, os, torch, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "origin"))
from action_head_patched import MiniCPMV_VLA_ActionHead

ORIGIN = os.path.join(os.path.dirname(__file__), "..", "origin")

def main():
    device, dtype = "cpu", torch.float32
    ah = MiniCPMV_VLA_ActionHead(
        hidden_size=1024, action_dim=80, state_dim=80,
        action_horizon=30, num_inference_timesteps=4, max_num_embodiments=32,
    ).to(dtype).to(device).eval()

    # 加载权重
    import safetensors.torch
    sd = safetensors.torch.load_file(os.path.join(ORIGIN, "model.safetensors"))
    ah_sd = {k.replace("action_head.", ""): v.float() for k, v in sd.items() if k.startswith("action_head.")}
    ah.load_state_dict(ah_sd, strict=True)
    print(f"Loaded {len(ah_sd)} action head params")

    # 单步导出封装
    class SingleStepPredict(torch.nn.Module):
        def __init__(self, ah): super().__init__(); self.ah = ah
        def forward(self, noisy_actions, vl_embs, state, timestep, embodiment_id):
            return self.ah._predict(noisy_actions, vl_embs, state, timestep, embodiment_id)

    model = SingleStepPredict(ah).to(device).eval()

    # Dummy inputs
    B = 1
    noisy_actions = torch.randn(B, 30, 80, dtype=dtype, device=device)
    vl_embs = torch.randn(B, 80, 1024, dtype=dtype, device=device)
    state = torch.randn(B, 80, dtype=dtype, device=device)
    timestep = torch.tensor([500], dtype=torch.long, device=device)
    embodiment_id = torch.zeros(B, dtype=torch.long, device=device)

    # Test forward
    with torch.no_grad():
        out = model(noisy_actions, vl_embs, state, timestep, embodiment_id)
    print(f"Output shape: {out.shape}, range: [{out.min():.4f}, {out.max():.4f}]")

    # Export
    onnx_path = os.path.join(os.path.dirname(__file__), "model_single.onnx")
    torch.onnx.export(
        model,
        (noisy_actions, vl_embs, state, timestep, embodiment_id),
        onnx_path,
        input_names=["noisy_actions", "vl_embs", "state", "timestep", "embodiment_id"],
        output_names=["denoised_actions"],
        opset_version=18,
        do_constant_folding=True,
    )
    print(f"ONNX exported: {onnx_path} ({os.path.getsize(onnx_path)/1024/1024:.1f} MB)")

    # Verify
    import onnx
    model_onnx = onnx.load(onnx_path)
    onnx.checker.check_model(model_onnx)
    print("ONNX checker passed")

    import onnxruntime as ort
    sess = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
    onnx_out = sess.run(None, {
        "noisy_actions": noisy_actions.numpy(),
        "vl_embs": vl_embs.numpy(),
        "state": state.numpy(),
        "timestep": timestep.numpy(),
        "embodiment_id": embodiment_id.numpy(),
    })
    diff = np.abs(out.numpy() - onnx_out[0])
    cos = np.dot(out.numpy().flatten(), onnx_out[0].flatten()) / (
        np.linalg.norm(out.numpy()) * np.linalg.norm(onnx_out[0]))
    print(f"ONNX Runtime: cos={cos:.6f}, max_diff={diff.max():.6e}")

    # Generate model_meta
    import json
    meta = {
        "model_name": "MiniCPM-RobotManip-ActionHead-SingleStep",
        "framework": "pytorch",
        "description": "Single _predict step of DiT action head. 4-step loop in SDK.",
        "inputs": [
            {"name": "noisy_actions", "shape": [1, 30, 80], "dtype": "float32", "preprocess": "Noisy action trajectory (diffusion step dependent)"},
            {"name": "vl_embs", "shape": [1, 80, 1024], "dtype": "float32", "preprocess": "VLM last hidden state"},
            {"name": "state", "shape": [1, 80], "dtype": "float32", "preprocess": "Robot state vector"},
            {"name": "timestep", "shape": [1], "dtype": "int64", "preprocess": "Diffusion timestep bucket (0-999)"},
            {"name": "embodiment_id", "shape": [1], "dtype": "int64", "preprocess": "Embodiment ID (0-31)"},
        ],
        "outputs": [{"name": "denoised_actions", "shape": [1, 30, 80], "dtype": "float32"}],
        "opset": 18,
        "onnx_size_bytes": os.path.getsize(onnx_path),
        "inference": "Run 4 times with timestep=[999,749,499,249] and noisy_actions = time*noise+(1-time)*actions",
    }
    with open(os.path.join(os.path.dirname(__file__), "model_meta_single.json"), "w") as f:
        json.dump(meta, f, indent=2)

if __name__ == "__main__":
    main()
