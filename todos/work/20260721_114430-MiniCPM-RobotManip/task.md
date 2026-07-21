# MiniCPM-RobotManip → AX650 部署任务

## 任务目标

将 HuggingFace `openbmb/MiniCPM-RobotManip` VLA 模型转换为 AX650 (NPU3) 可用的 AXMODEL 交付包。

## 输入参数

| 参数 | 值 |
|------|-----|
| SOURCE | https://hf-mirror.com/openbmb/MiniCPM-RobotManip |
| TARGET_HARDWARE | AX650 |
| NPU_MODE | NPU3 |
| MODEL_NAME | MiniCPM-RobotManip |
| TASK_DIR | /opt/rzyang/Github/Magnetar/todos/work/20260721_114430-MiniCPM-RobotManip |
| BOARD | N/A (跳过 RUNONBOARD) |
| PULSAR2_IMAGE | pulsar2:20260520-temp-61099061-lite |
| HF_ENDPOINT | https://hf-mirror.com |
| SDK_LANG | both |

## 阶段状态

| 阶段 | 状态 | 备注 |
|------|------|------|
| ACQUIRE | ✅ 完成 | 模型下载完成 (3.4GB safetensors) |
| INIT | 🔄 进行中 | 目录结构和审计文件初始化 |
| EXPORT | ⬜ 待执行 | |
| TOOLCHAIN | ⬜ 待执行 | |
| COMPILE | ⬜ 待执行 | |
| SIMULATE | ⬜ 待执行 | |
| SDK-GEN | ⬜ 待执行 | |
| RUNONBOARD | ⬜ N/A | 无 BOARD，自动跳过 |
| PACKAGE | ⬜ 待执行 | |

## ACQUIRE 执行记录

- 时间: 2026-07-21 11:44-11:55
- 下载方式: huggingface_hub.snapshot_download (hf-mirror)
- 下载文件: 21个文件，模型权重 model.safetensors 3.4GB
- 产物: cache/acquire/manifest.json

## EXPORT 执行记录

- 时间: 2026-07-21 12:00-12:46
- 导出模块: Action Head (DiT), VLM 部分未导出 (Mamba SSM 不支持)
- ONNX opset: 18
- ONNX 大小: 5.60 MB
- 验证: checker ✅, ONNXRT ✅, cosine=1.0000
- 校准数据: 5 组 (VLM 处理合成场景图片生成)
- 产物: model.onnx, model_meta.json, calib_data/, export_report.md
- 修复: PyTorch 2.13 expand bug (action_head_patched.py)

## TOOLCHAIN 执行记录

- 时间: 2026-07-21 12:47-12:53
- Pulsar2: pulsar2:20260520-temp-61099061-lite (v6.0, commit 61099061)
- BSP: /opt/rzyang/sdk/AX650_SDK_V3.10.2_20260513151335.tgz (3.5GB, 已有)
- 交叉编译器: /usr/local/aarch64-none-linux-gnu-arm-9.2-2019.12/bin/aarch64-none-linux-gnu-g++ (GCC 9.2.1)
- AX_RUNTIME_TYPE: axengine (无 BOARD, 默认)
- AX runtime: /opt/rzyang/Github/ax650n_bsp_sdk/msp/out/
- 产物: sdk/cpp/toolchain-aarch64.cmake
