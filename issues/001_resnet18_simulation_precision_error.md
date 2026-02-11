# Issue 001: ResNet18 仿真精度问题

## 问题描述
在ResNet18模型部署过程中，仿真阶段发现量化模型与原始ONNX模型输出存在较大差异：
- Cosine Similarity: 0.687 (目标 >0.99)
- MSE: 1.163 (目标 <0.1)
- Top-5 overlap: 1/5 (目标 4-5/5)
- Relative Error: 2.383

## 环境信息
- **模型**: torchvision.models.resnet18 (ImageNet预训练)
- **目标芯片**: AX650 NPU1
- **Pulsar2版本**: 5.1-patch1
- **校准数据**: 4张COCO图像，预处理与推理一致

## 初始配置 (pulsar2_config.json)
```json
"input_processors": [
  {
    "tensor_name": "input",
    "src_dtype": "U8",
    "mean": [],
    "std": []
  }
]
```

## 问题分析
1. **输入数据类型不匹配**: ONNX模型期望float32输入（已包含归一化预处理），但AXModel配置为U8输入
2. **预处理链不一致**:
   - ONNX: 图像 → Resize/CenterCrop → ToTensor → Normalize → 模型
   - AXModel配置: U8输入 → Dequantize(scale=1, zero=0) → 模型
   - 缺失归一化步骤
3. **量化误差放大**: 输入范围不匹配导致量化误差被放大

## 调试过程
### 第一次仿真 (失败)
- 输入: 随机正态分布数据 (float32)
- 结果: 精度差异显著
- 分析日志发现: `tensor: input, (1, 3, 224, 224), U8`

### 配置修正
修改 `pulsar2_config_v2.json`:
```json
"input_processors": [
  {
    "tensor_name": "input",
    "src_dtype": "FP32",  // 改为FP32
    "mean": [],
    "std": []
  }
]
```

### 第二次编译与仿真 (成功)
- 重新编译模型
- 使用相同真实图像输入
- 结果: Cosine Similarity 0.998, MSE 0.027, Top-5 overlap 4/5

## 根本原因
ONNX导出时包含了完整的预处理链（包括归一化），因此模型期望的输入是**归一化后的float32数据**。初始配置中`src_dtype="U8"`导致：
1. 运行时输入被当作U8处理（0-255）
2. Dequantize操作简单地将U8转换为float32（scale=1, zero=0）
3. 输入数据范围错误（0-255 vs 归一化后的-2~2范围）
4. 模型内部归一化层接收到错误范围的输入，导致输出偏差

## 解决方案
1. **正确配置输入数据类型**: 根据模型期望设置`src_dtype`
   - 如果模型包含归一化: `src_dtype="FP32"`
   - 如果模型不包含归一化: 需要配置`mean`/`std`参数
2. **保持预处理一致性**: 确保校准数据集与推理输入处理完全一致
3. **验证配置**: 编译后检查日志中的输入张量信息

## 经验教训
1. **输入配置至关重要**: `src_dtype`必须与模型期望严格匹配
2. **预处理链分析**: 导出ONNX前需明确模型包含哪些预处理操作
3. **校准数据一致性**: 校准数据必须与推理时输入数据经过完全相同处理
4. **调试方法**: 使用真实数据而非随机数据进行比较，更容易发现问题

## 相关文档
- Pulsar2输入处理器配置: https://pulsar2-docs.readthedocs.io/zh-cn/latest/user_guides_advanced/advanced_build_guides.html#input-processors
- 精度调试指南: https://pulsar2-docs.readthedocs.io/zh-cn/latest/appendix/precision_debug_guides.html

## 解决状态
✅ 已解决 - 通过修正`src_dtype`配置实现精度达标