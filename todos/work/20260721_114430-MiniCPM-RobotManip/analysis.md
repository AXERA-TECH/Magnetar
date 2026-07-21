# MiniCPM-RobotManip 技术分析

## 模型来源

- HuggingFace: openbmb/MiniCPM-RobotManip
- 下载端点: https://hf-mirror.com
- 模型类型: VLA (Vision-Language-Action)

## 目标芯片

AX650, NPU mode=NPU3

## 模型架构

### VLM 部分 (MiniCPMV4_6ForConditionalGeneration)
- Text backbone: Qwen3.5-style (24层, hidden=1024, intermediate=3584)
- 注意力: linear_attention (每4层一个full_attention), num_kv_heads=2
- Vision backbone: 27层, hidden=1152, patch=14, 输入image_size=980
- Merger: kernel [2,2], 1次, vision tokens数: (980/14)^2/4 = 1225
- dtype: bfloat16

### Action Head 部分 (DiT Diffusion)
- 架构: Diffusion Transformer, 16层, cross_attn_dim=1024
- 输入: VLM hidden_states[-1] (1024-dim) + robot state (80-dim)
- 输出: action trajectory (30步 × 80维)
- 推理: 4步去噪 (num_inference_timesteps=4)
- 多embodiment支持 (max 32)
- dtype: float32

## 已知约束和假设

1. **动态shape**: VLM部分输入image size可变，文本长度可变 — 需要固定shape导出
2. **复杂算子**: linear_attention (Mamba-style), RoPE, SiLU, GELU等 — Pulsar2是否支持需验证
3. **DiT扩散**: Action head含迭代去噪循环 — 需展平为单步forward或拆分子图
4. **模型巨大**: 3.4GB bf16 → ONNX可能更大，需评估是否超出AX650内存
5. **VLA特殊性**: 非标准分类/检测，精度验证需自定义指标

## 环境摘要

- Python: 3.12.12
- uv: 0.10.2
- Docker: 29.1.3
- Pulsar2: pulsar2:20260520-temp-61099061-lite (lite, 3.09GB)
- cmake: 3.31.5
- git: 2.34.1
- 磁盘: 11T 可用

## EXPORT 阶段分析

### 导出决策
- VLM 部分 (MiniCPMV4_6): 18/24 层使用 linear_attention (Mamba SSM)，Pulsar2/AX650 NPU 不支持，保留在 CPU
- Action Head (DiT): 纯 Transformer + MLP，算子兼容性好，导出为 ONNX

### 校准数据
- 使用 VLM 处理合成场景图片生成真实 hidden states 分布
- 优势: 经过 vision encoder + text encoder + cross-attention，分布比随机噪声更真实
- vl_embs 统计: mean≈0, std≈0.43

## TOOLCHAIN 阶段分析

- Pulsar2 lite 镜像, 版本 v6.0
- AX650 BSP SDK 已解压, 但交叉编译器和 AX runtime 使用系统已有路径
- 无 BOARD, AX_RUNTIME_TYPE=axengine
- 交叉编译器 GCC 9.2.1, armv8-a, 通用兼容性好
