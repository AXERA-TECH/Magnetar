
# AX-Samples 模型部署工作流 (AX-Samples Deployment Workflow)

该工作流旨在将原始浮点模型转换为可运行在 AX 芯片上的量化模型，并在硬件开发板上完成验证。

## 工作流准则

**核心原则：**

* **顺序执行**：必须按照 INIT → EXPORT → COMPILE → VERIFY → SIMULATION → RUNONBOARD 顺序执行。
* **强制确认**：在每个标记有 **STOP** 的地方必须获得用户确认或输入。
* **状态记录**：所有执行过程、错误分析必须记录在 `task.md` 和 `analysis.md` 中。
* **环境隔离**：所有操作必须在指定的任务工作目录下进行。所有的debug文件(编译输出， 仿真文件， 调试python脚本)，中间文件必须放在 "$TASK_DIR/cache" 目录下，禁止污染环境. 预期任务工作目录下结构如下:
  ```
      TASK_DIR: 
            - ax-samples/
            - cache/
            - compile/
            - origin/
            - analysis.md
            - task.md
  ```
* **问题记录**：在调试时遇到的所有问题，解决后都放到 `issues` 目录下, 新建一个文档， 命名规则参照为`序号_模型名_阶段_问题简述.md`，如`000_mobilenet_export_acc_error.md`；
---

### INIT：初始化与环境检查

1. **创建工作目录**：
* 获取时间戳：`TIMESTAMP=$(date +%Y%m%d-%H%M%S)`
* 获取模型名称缩写（用户提供或从路径提取）：`MODEL_NAME=[model-name]`
* 创建目录结构：
```bash
TASK_DIR="todo/work/${TIMESTAMP}-${MODEL_NAME}"
mkdir -p "$TASK_DIR/origin" "$TASK_DIR/compile" "$TASK_DIR/simulate" "$TASK_DIR/ax-samples" "$TASK_DIR/cache"

```


2. **初始化任务文件**：
* 创建 `${TASK_DIR}/task.md`（参照下方模板）并设置 **Status: INIT**。拷贝todo/todo.md原始内容到文件开头部分。
* 创建 `${TASK_DIR}/analysis.md` 用于记录技术细节。
* 上述创建完成后，清空 todo/todo.md 的内容。

3. **环境预检**：
* **工具检查**：执行 `pulsar2 --version`。如果不可用，**STOP** → "pulsar2 命令未找到。是否继续？(y/n)"
* **资源检查**：确认模型路径/链接。如果是链接则下载至 `origin/`；如果是路径则拷贝至 `origin/`。


4. **STOP** → "环境初始化完成，准备开始导出阶段吗？(y/n)"


---

### EXPORT：模型导出与准备

**约束**： 工作目录为 `"$TASK_DIR/origin"` , 所有生成的文件必须放在这个工作目录下

1. **执行导出任务**：
* 确认模型任务类型，模型名，是否需要重新安装环境。
* 如果依赖环境，需要先安装环境。
* 
* 编写 `inference.py`（基于 onnxruntime）进行初步推理验证。inference.py 只使用单个数据推理，必须使用真实数据。
* 将 PyTorch 模型转换为 ONNX 格式。导出模型使用单独python文件
* 准备量化数据集（Calibration Dataset）。
  - 数据集的格式参考 `https://pulsar2-docs.readthedocs.io/zh-cn/latest/user_guides_advanced/advanced_build_guides.html#custom-calib-dataset` ，需要保证与推理时一致。
  - 数据集需要根据模型任务，使用真实数据，如果用户没有提供，需要与用户交互确认是否使用随机数据或者用户给出路径或者获取数据集的方法，一般使用4/16/32张数据集。
  - 导出数据集使用单独python文件
  - 配置文件中如果配置了 mean/std参数，则在推理时，期望输入是不做预处理的，这时要十分注意配置，在模型中只会做一次预处理；如果是pytorch模型，有些模型会先做一次 -0/255的归一化操作，而后面又会做一次归一化，比如 "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225] ，这时不能直接配置 mean/std为 [0.485, 0.456, 0.406] 和 [0.229, 0.224, 0.225]，而是它们乘上255
* 只支持静态shape，batch也是；

2. **验证输出文件**：
* 确认生成：`model_name.onnx`
* 确认生成：`calibration_data.zip`
* 确认生成：`inference.py`


3. **记录分析**：在 `analysis.md` 中记录算子兼容性情况。
4. **STOP** → "模型导出成功。推理示例是否运行正常？(y/n)"

---

### COMPILE：模型编译 (pulsar2)

**约束**： 工作目录为 `"$TASK_DIR/compile"` , 所有生成的文件必须放在这个工作目录下

1. **设置状态**：更新 `task.md` 状态为 **Status: Compiling**。
2. **准备配置文件和量化数据集**：将配置文件和校准数据集拷贝到 `${TASK_DIR}/compile/` 下
2. **执行编译**：
* 使用 `pulsar2 build` 命令针对目标芯片进行编译。
* 将编译产物存放在 `${TASK_DIR}/compile/`。


3. **错误处理**：
* 如果编译报错，必须分析错误日志（如算子不支持、内存溢出等）。
* 将错误详情记录至 `analysis.md`。
* **STOP** → "编译遇到错误。已记录分析。尝试修复还是终止？(fix/exit)"


4. **产物验证**：确认生成 `compiled.axmodel`。
5. **拷贝**： 仿真完成后，将产物和配置文件放到 `${TASK_DIR}/compile/output` 目录下，如果没有该目录，则创建 
6. **STOP** → "编译成功。是否进入仿真阶段？(y/n)"

---

### VERIFY & SIMULATION：精度验证与仿真
**约束**： 工作目录为 `"$TASK_DIR/simulate"` , 所有生成的文件必须放在这个工作目录下

1. **一致性检查**：
* 仿真输入、 仿真输出、调试脚本等所有仿真相关文件放在 "$TASK_DIR/simulate" 下 
* 使用仿真工具对比 ONNX 输出与 `axmodel` 仿真输出。
* 记录精度损失情况。
* 如遇到精度差异较大，参考 `https://pulsar2-docs.readthedocs.io/zh-cn/latest/appendix/precision_debug_guides.html` 进行调试


2. **STOP** → "仿真精度是否达标？(y/n)"

---

### RUNONBOARD：板端运行验证

1. **部署准备**：
* 更新 `task.md` 状态为 **Status: RunningOnBoard**。
* 自动修改代码：将 `${TASK_DIR}/inference.py` 中的 `import onnxruntime as ort` 替换为 `import axengine as ort`。


2. **推送文件**：
* 使用 `scp` 将 `compiled.axmodel` 和修改后的 `inference.py` 推送到开发板指定目录。


3. **执行推理**：
* 通过 SSH 在板端运行推理程序。


4. **结果比对**：
* 收集板端输出结果，与 EXPORT 阶段的浮点模型结果进行对比。


5. **更新状态**：
* 完成所有任务项后，将 `task.md` 状态改为 **Status: Done**。


6. **STOP** → "板端验证完成。结果是否符合预期？(y/n)"

---

## 附件：Task.md 模板

```markdown
# Task: [Model Name] Deployment

**Status:** INIT / EXPORTING / COMPILING / RUNNING
**Agent PID:** [Bash(echo $PPID)]

## 基础信息
- **原始模型**: [Path/URL]
- **目标芯片**: [e.g. AX620E / AX650]
- **工作目录**: [TASK_DIR]

## 实施进度
- [ ] **INIT**: 环境检查与资源下载
- [ ] **EXPORT**: ONNX 导出与验证
- [ ] **COMPILE**: pulsar2 编译 axmodel
- [ ] **SIMULATION**: 仿真精度对比
- [ ] **RUNONBOARD**: 开发板实测验证

## 编译日志摘录
> [记录关键的编译参数或报错片段]

## 运行结果
- **浮点模型输出**: [Summary]
- **板端模型输出**: [Summary]
- **精度偏差**: [Percentage]

```

---
