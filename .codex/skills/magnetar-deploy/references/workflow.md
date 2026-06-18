# Magnetar Codex 工作流

## 总则

工作流用于将原始浮点模型转换为可运行在 AX 芯片上的量化模型，并完成仿真和板端验证。

严格顺序：

`INIT -> EXPORT -> COMPILE -> SIMULATE -> RUNONBOARD`

每个阶段都要维护：

- `TASK_DIR/task.md`: 状态、进度、关键产物、命令摘要、结果摘要。
- `TASK_DIR/analysis.md`: 技术分析、错误原因、配置取舍、精度判断依据。

推荐任务目录：

```text
TASK_DIR/
  origin/
  export/
  compile/
  simulate/
  ax-samples/
  cache/
  task.md
  analysis.md
```

历史经验记录放在仓库根目录 `issues/`。新增文件命名：`序号_模型名_阶段_问题简述.md`，例如 `002_yolov5_compile_unsupported_resize.md`。

## INIT: 初始化与环境检查

工作目标：创建隔离工作区，准备原始模型，确认工具链可用性。

步骤：

1. 推断或询问 `MODEL_NAME`、`REPO`、`TASK_DIR`、`TARGET_HARDWARE`。
2. 默认使用 `TIMESTAMP=$(date +%Y%m%d-%H%M%S)` 创建 `todos/work/${TIMESTAMP}-${MODEL_NAME}`。
3. 创建 `origin/ export/ compile/ simulate/ ax-samples/ cache/`。
4. 创建 `task.md`，状态设为 `INIT`，模板可参考仓库根目录 [task.md](../../../../task.md)。
5. 创建 `analysis.md`，记录任务目标、输入来源、环境信息。
6. 将 `REPO` clone 或复制到 `origin/`；如果是单个模型文件，复制到 `origin/`。
7. 执行环境预检：
   - `pulsar2 --version`
   - `python --version`
   - 必要时检查 `conda`、`uv`、`docker`、`ssh`、`scp`
8. 如果 `pulsar2` 不可用，记录问题并进入 STOP。

STOP: 环境初始化完成或发现阻塞后，询问是否进入 EXPORT。

## EXPORT: 模型导出与 ONNX 验证

工作目录：`TASK_DIR/export/`

工作目标：理解原始模型，导出动态 ONNX 和静态 ONNX，生成真实校准集，并验证 ONNX 与原始模型输出一致。

环境建议：

- 优先复用项目已有环境。
- 若需新建环境，优先使用 `uv`，虚拟环境放在 `TASK_DIR/cache/` 或阶段目录下。
- `numpy < 2.0`
- `torch <= 2.6`，无 GPU 需求时优先 CPU 版本。
- 安装 `onnxruntime`、`onnx`、`onnxscript`。

步骤：

1. 阅读 `origin/` 中 README、推理脚本、测试代码和模型源码，明确：
   - 模型任务类型
   - 输入名、shape、dtype、layout
   - 输出含义
   - 预处理和后处理
   - 是否包含多组件、动态长度、Transformer KV Cache
2. 编写 `test-torch.py` 或等价原始模型推理脚本：
   - 使用 `argparse`
   - 尽量提供默认参数
   - 使用真实输入数据
   - 输出结果摘要
   - 配套写 `test-torch.md`
3. 编写 `export-dynamic-onnx.py`：
   - 使用 `argparse`
   - `torch.onnx.export(..., dynamo=False)`
   - 需要动态轴时使用 `dynamic_axes`
   - 多模型或多组件时允许分组件导出
   - 需要改模型时优先 monkeypatch，不直接修改原工程
   - 增加与 Torch 或原始模型的对分校验
4. 编写 `export-static-onnx.py`：
   - 静态 shape，不使用 `dynamic_axes`
   - batch 静态
   - `dynamo=False`
   - 给出推荐输入长度或固定尺寸
   - 生成静态 ONNX 并进行对分
5. 输出文档：
   - `model_structure.md`
   - `export-dynamic-onnx.md`
   - `export-static-onnx.md`
   - `workaround.md`，记录为导出成功做出的限制或取舍
6. 生成校准集脚本 `generate-data.py`：
   - 优先真实数据：项目样例、用户提供路径、可下载小样本。
   - 如果只能用随机数据，必须 STOP 等待用户确认。
   - 生成目录：

```text
calib_data/
  input_name_0/
    data_index_0.npy
    data_index_1.npy
  input_name_1/
  input_name_0.tar.gz
  input_name_1.tar.gz
```

7. 预处理一致性检查：
   - 如果 ONNX 内已经包含归一化，Pulsar2 `src_dtype` 和 mean/std 不能重复处理。
   - 如果配置 mean/std，则运行时输入通常应是不预处理的原始输入。
   - PyTorch 常见 `ToTensor` 后再 Normalize 的参数若迁移到 0-255 输入侧，mean/std 需要乘 255。
8. 在 `task.md` 记录静态 ONNX 路径、校准集路径、对分结果。
9. 在 `analysis.md` 记录算子兼容性、shape 决策、预处理链。

若导出失败，记录错误和已尝试方案；可询问用户是否允许启动并行分析或改造模型。

STOP: ONNX 导出和推理示例验证完成后，询问是否进入 COMPILE。

## COMPILE: Pulsar2 编译

工作目录：`TASK_DIR/compile/`

工作目标：用 Pulsar2 将静态 ONNX 编译为 `compiled.axmodel`。

步骤：

1. 更新 `task.md` 状态为 `COMPILING`。
2. 复制静态 ONNX、校准集、必要样本到 `compile/`。
3. 编写 `pulsar2_config.json`，字段至少明确：
   - `input`
   - `output_dir`
   - `output_name`
   - `model_type`
   - `target_hardware`
   - `npu_mode`
   - `input_shapes`
   - `quant.input_configs`
   - `input_processors`
4. 禁止配置 `"highest_mix_precision": true`。
5. 校验 `src_dtype`、layout、mean/std 与 EXPORT 阶段预处理一致。
6. 执行 `pulsar2 build --config pulsar2_config.json` 或当前 Pulsar2 版本要求的等价命令。
7. 日志保存到 `compile/` 或 `cache/`。
8. 若编译失败：
   - 分析是否为 ONNX op 不支持、shape 不支持、内存溢出、配置错误、校准集错误。
   - 记录到 `analysis.md`。
   - 若需要改 ONNX，回到 EXPORT 前必须 STOP。
9. 确认产物：
   - `compiled.axmodel`
   - 量化对分表或 quant csv，如有
   - 编译日志
10. 将最终产物和配置复制到 `compile/output/`。
11. 在 `task.md` 记录：
   - axmodel 路径
   - Pulsar2 版本或 Docker 镜像版本
   - 目标芯片和 npu mode
   - MACS、max cycles、量化对分表路径，如可获得

STOP: 编译成功或遇到编译错误后，询问是否进入 SIMULATE、修复或终止。

## SIMULATE: 仿真与精度验证

工作目录：`TASK_DIR/simulate/`

工作目标：使用同一输入对比 ONNX 输出和 AXMODEL 仿真输出，判断量化精度是否达标。

步骤：

1. 准备真实测试输入，确保与 EXPORT/COMPILE 预处理链一致。
2. 编写并保留仿真脚本：
   - ONNX 推理脚本
   - `pulsar2 run` 或等价 AXMODEL 仿真脚本
   - 输出对比脚本
3. 记录输入样本路径、输出 tensor 名称、shape、dtype。
4. 对比指标按任务选择：
   - 分类：cosine similarity、Top-1/Top-5、平均绝对误差、最大绝对误差。
   - 检测：框坐标误差、类别一致性、NMS 前后差异、mAP 小样本 sanity check。
   - 分割：像素准确率、mIoU 小样本 sanity check、logits cosine。
   - 通用张量：cosine、MSE、MAE、max abs diff、分位数误差。
5. 不要只依赖相对误差；当参考值接近 0 时，相对误差会误导。
6. 若精度不达标，优先排查：
   - 输入 dtype 是否匹配，如 `FP32` vs `U8`
   - mean/std 是否重复或缺失
   - layout 是否混淆 NCHW/NHWC
   - 校准集是否真实且覆盖任务分布
   - ONNX 导出是否与原模型一致
   - 不支持 op 是否被错误替代
7. 生成 `simulate-report.md`，记录测试过程、指标、结论和下一步。
8. 更新 `task.md` 和 `analysis.md`。

STOP: 仿真精度验证完成后，询问是否进入 RUNONBOARD 或继续调试。

## RUNONBOARD: 板端运行验证

工作目录：`TASK_DIR/ax-samples/`

工作目标：将模型和推理脚本部署到 AX 开发板，运行并与仿真/ONNX 输出比较。

步骤：

1. 确认用户提供或环境已有板端信息：
   - host
   - user
   - port
   - remote workdir
   - runtime 依赖
2. 更新 `task.md` 状态为 `RUNNING_ON_BOARD`。
3. 准备板端推理脚本。可基于 EXPORT 阶段 `inference.py`，但不要原地破坏源文件：
   - 复制到 `ax-samples/`
   - 将 `import onnxruntime as ort` 替换为 `import axengine as ort`，或按 axengine 实际 API 调整
4. 使用 `scp` 推送：
   - `compiled.axmodel`
   - 推理脚本
   - 测试输入
   - 必要依赖文件
5. 使用 `ssh` 运行推理，保存 stdout/stderr。
6. 拉回输出结果，与 SIMULATE/ONNX 输出对比。
7. 记录性能、输出一致性、板端环境。
8. 完成后将 `task.md` 状态改为 `DONE`。

STOP: 板端验证完成后，询问结果是否符合预期；如果不符合，记录问题并进入调试。

## Issue 沉淀模板

```markdown
# Issue NNN: [模型] [阶段] [问题简述]

## 问题描述

## 环境信息

## 复现步骤

## 关键日志

## 根本原因

## 解决方案

## 经验教训

## 相关产物
```

## 已知经验

- MobileNetV2 分类输出中参考值接近 0 时，相对误差可能很大，但 cosine 和 Top-k 正常；分类任务不要只用相对误差判断。
- ResNet18 曾因 ONNX 期望归一化后的 FP32 输入，但 Pulsar2 配置为 `src_dtype="U8"` 导致精度失败；修正为与模型输入一致的 `FP32` 后达标。
- 预处理链是最常见问题来源。每次编译前必须明确：预处理在模型外、ONNX 内、还是 Pulsar2 input processor 内完成。
