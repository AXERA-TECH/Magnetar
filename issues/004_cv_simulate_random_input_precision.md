# [004] CV 模型 SIMULATE 精度异常：随机输入 + 随机校准导致 cosine 偏低

## 现象
| 模型 | cosine_sim | 阈值 | 判定 |
|---|---|---|---|
| hf_resnet50 | 0.9994 | 0.99 | PASS |
| hf_mobilenet | 0.982 | 0.99 | 略低于阈值 |
| local_efficientnet | **0.173** | 0.99 | 严重崩溃 |

## 根因
benchmark 脚本为追求全自动，**校准数据和仿真输入都用 `np.random.rand` 随机生成**，
没有用真实图像、也没有走模型真实预处理链（resize/normalize/mean-std）。

后果：
1. **校准分布失真**：MinMax 校准在随机噪声上统计激活范围，与真实图像的激活分布差异大，
   量化 scale 选取偏差，量化误差被放大。
2. **模型对分布敏感度不同**：
   - ResNet（BN 多、激活平滑）对输入分布不敏感 → 0.9994 仍达标。
   - MobileNet（depthwise conv，通道间 scale 差异大）→ 0.982 临界。
   - EfficientNet（SE 注意力 + swish，激活动态范围大）→ 0.173 崩溃。

## 这不是模型/工具的问题，是评测方法的问题
真实部署时应：
- 校准集：用 16/32 张**真实图像**，经模型标准预处理（如 ImageNet mean/std）。
- 仿真输入：同一张真实图像，ONNX 和 axmodel 用**完全相同**的预处理结果。

## 验证 U8-first 策略的正确入口
mobilenet 的 0.982（仅略低）正是 U8-first 策略 Pass 2/3 的目标场景：
开 `precision_analysis: PerLayer` 找出量化损失最大的层（通常是 depthwise conv 或 SE 模块），
仅对这些层升 U16，其余保持 U8。但前提是**先用真实数据校准**，否则升 U16 也救不回 0.173。

## 解决方向
1. CALIBRATION：支持从 `models.yaml` 指定真实校准图像目录，按模型预处理生成校准集。
2. SIMULATE：用真实图像，ONNX/axmodel 共享预处理输出。
3. 精度不足时按 issues 中 U8-first 三 Pass 流程升精度。

## 复现
`bash todos/benchmark/run_one.sh local_efficientnet`  # cosine ~0.17

## 状态
已识别为评测方法局限。benchmark 脚本默认随机数据仅用于打通流程，精度数字不代表真实部署精度。
