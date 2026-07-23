---
name: sdk-gen
description: Hidden stage for magnetar. Generate customer-facing Python and C++ inference SDKs from model_meta.json and AXMODEL artifacts.
---

# SDK-GEN

## YOLO 系列模型检测

在生成 SDK 前，必须检测当前模型是否为 YOLO 系列检测/姿态模型。满足以下任一条件即判定为 YOLO 模型：

- 模型名称包含 `yolo`（大小写不敏感）、`YOLOv5`、`YOLOv8`、`YOLO11`、`yolov5`、`yolov8`、`yolo11`
- `model_meta.json` 中模型任务类型为 `detection` 或 `pose`，且模型架构描述提及 YOLO
- `task.md` 中记录的 `MODEL_NAME` 或 SOURCE 信息包含 YOLO 标识

判定为 YOLO 模型时，SDK 必须基于 libdet.axera（https://github.com/AXERA-TECH/libdet.axera.git）实现推理后处理，不得手写 YOLO decode/NMS 逻辑。非 YOLO 模型按原有方式生成 SDK。

目标：按顺序生成 Python 和 C++ 客户 SDK，分别验证后输出 sdk_report.md。SDK 自带的 README.md 必须详尽到客户无需查看其他文档即可安装环境、编译、运行示例。

## Python SDK

目录：`TASK_DIR/sdk/python/<model_name>_sdk/`

必须包含：

- `__init__.py`
- `inference.py`
- `preprocess.py`
- `postprocess.py`

上级目录 `TASK_DIR/sdk/python/` 必须包含：
- `requirements.txt`（顶层依赖，如 pyaxengine）
- `example.py`（可独立运行的推理示例，import <model>_sdk 调用 SDK 类）
- `README.md`（Python SDK 总览，含环境安装和快速运行）

### 通用 Python SDK 要求

- 必须使用 `pyaxengine` 的 `axengine.InferenceSession` 运行 AXMODEL。
- 默认 provider 必须显式设置为 `AxEngineExecutionProvider`；该 provider 不可用时，才允许按 `axengine.get_available_providers()` 选择 fallback provider，并在报告中记录。
- 顶层 `requirements.txt` 必须说明 `pyaxengine` 来源：`https://github.com/AXERA-TECH/pyaxengine`。
- 从 `model_meta.json` 读取输入输出信息，不硬编码无法追溯的 shape。
- 必须提供可复用 SDK 类或等价封装，example 只负责实例化该类、加载输入、调用方法和展示结果。
- 示例必须按模型实际任务语义编写；分类模型输出 top-k 类别/分数，检测模型输出框/类别/置信度，语音模型输出文本或任务结果。不得只打印 tensor shape 或一堆原始数字作为 demo。
- `python -c "import <model_name>_sdk"` 必须通过。
- 不得调用 `ax_run_model` 实现 Python SDK 推理。

### YOLO 模型 Python SDK 要求

对于 YOLO 系列模型，后处理逻辑必须通过 libdet.axera 的 Python 绑定实现：

1. **依赖声明**：顶层 `requirements.txt` 中需注明 libdet.axera 的获取方式（`git clone https://github.com/AXERA-TECH/libdet.axera.git`），因为 pydet 通过 ctypes 调用编译产物 `libdet.so`。
2. **SDK 结构**：在 `<model_name>_sdk/` 下创建 `pydet/` 子目录，包含从 libdet.axera 仓库 `pydet/` 目录复制的以下文件：
   - `pydet.py` — AXDet 封装类
   - `pyaxdev.py` — 设备枚举封装
   - `__init__.py`
3. **预处理 (preprocess.py)**：输入图像 resize 至模型输入尺寸，**保持 BGR 不做 RGB 转换**（匹配 Pulsar2 校准的 BGR 输入），保持 uint8 格式。归一化由 libdet 内部 std=1/255 完成。
4. **推理 (inference.py)**：
   - **std 设置**：必须传入 `std=[1/255, 1/255, 1/255]` 以匹配校准归一化。`pydet.AXDet` 默认 std=[1,1,1]（无归一化），需要显式覆盖。
   - 使用 `pydet.AXDet` 类完成端到端推理（加载模型 + 推理 + 后处理），不单独调用 InferenceSession
   - 示例：
     ```python
     from .pydet import AXDet, ModelType
     detector = AXDet(model_path="model.axmodel", model_type=ModelType.ax_det_model_type_yolo11,
                      num_classes=11, threshold=0.25,
                      mean=[0,0,0], std=[0.00392157, 0.00392157, 0.00392157])
     objects = detector.detect(image_rgb_uint8)
     # objects: list of Object(box=[x,y,w,h], score=float, label=int, kpts=[])
     ```
5. **示例 (example.py)**：位于 `TASK_DIR/sdk/python/example.py`。加载图像、调用 SDK 类、绘制检测框并标注类别和置信度、保存结果图像。通过 `from <model>_sdk import ...` 调用 SDK。
6. **模型类型映射**：
   | YOLO 变体 | ModelType 枚举值 |
   |-----------|-----------------|
   | YOLOv5 | `ax_det_model_type_yolov5` (0) |
   | YOLOv8 | `ax_det_model_type_yolov8` (1) |
   | YOLOv8-Pose | `ax_det_model_type_yolov8_pose` (2) |
   | YOLO11 | `ax_det_model_type_yolo11` (3) |
   | YOLO11-Pose | `ax_det_model_type_yolo11_pose` (4) |

## Python SDK README.md

`TASK_DIR/sdk/python/README.md` 必须包含：

1. **环境要求**：Python 版本、系统依赖（如 libgl1）。
2. **安装步骤**：
   - 完整的 `pip install -r requirements.txt` 命令。
   - 若 `pyaxengine` 需从源码安装，给出完整的 `git clone` + `pip install` 命令。
   - YOLO 模型额外步骤：`git clone` libdet.axera + 编译 `libdet.so`（或从预编译包获取）。
3. **快速运行**：完整命令行示例，含输入文件格式要求。
4. **API 说明**：SDK 类的初始化参数、推理方法签名、返回值结构。
5. **输入预处理说明**：resize 策略、归一化参数、颜色通道顺序。

## C++ SDK

目录：`TASK_DIR/sdk/cpp/`

必须包含：

- `bin/visdrone_detect`（预编译 aarch64 可执行程序）
- `include/`（libdet.h、ax_devices.h）
- `lib/libdet.so`（预编译 aarch64 共享库）
- `README.md`（详见下方 [C++ SDK README.md](#c-sdk-readmemd)）

### 通用 C++ SDK 要求

- CMake 支持本机构建和 aarch64 交叉编译；存在交叉编译工具链时必须执行交叉编译验证。
- C++ SDK 必须直接调用 AX runtime API，链接库根据 `AX_RUNTIME_TYPE` 选择：`axcl` 时链接 `libaxcl_rt.so`，`axengine` 时链接 `libax_engine.so`/`libax_sys.so`。
- AX runtime 头文件/库未知时，用变量占位：`AX_RUNTIME_ROOT`，目录应包含 `include/` 和 `lib/`。
- C++ 工程模板参考：https://github.com/ml-inory/Template.axera/tree/main
- 必须生成可复用 C++ 类，例如 `<ModelName>Runner`、`<ModelName>Classifier` 或任务对应命名；AX runtime 的加载、IO 分配和推理封装在类内部。
- `examples/` 中的程序只能实例化 SDK 类并调用公开方法，不应把主要推理逻辑写在 example 里。
- 示例必须按模型实际任务语义编写；分类模型输出 top-k 类别/分数，检测模型输出框/类别/置信度，语音模型输出文本或任务结果。不得只打印 tensor shape 或一堆原始数字作为 demo。
- 不得调用 `ax_run_model` 实现 C++ SDK 推理。
- 有工具链时执行交叉编译；否则至少执行 `cmake -S . -B build`。

### YOLO 模型 C++ SDK 要求

对于 YOLO 系列模型，C++ SDK 必须集成 libdet.axera 实现端到端推理（加载 AXMODEL + 推理 + 后处理）：

1. **集成方式**：将 libdet.axera 作为源码依赖引入 SDK 工程。
   - 在 `CMakeLists.txt` 中通过 FetchContent 引入 libdet.axera
   - 若网络不可用，则将 libdet.axera 源码复制到 `sdk/cpp/third_party/libdet.axera/` 目录，使用 `add_subdirectory` 引入
2. **CMakeLists.txt FetchContent 模板**：
   ```cmake
   include(FetchContent)
   FetchContent_Declare(
       libdet
       GIT_REPOSITORY https://github.com/AXERA-TECH/libdet.axera.git
       GIT_TAG main
   )
   FetchContent_MakeAvailable(libdet)
   target_link_libraries(<target> det ${OpenCV_LIBS})
   ```
3. **examples/ 程序模板**（使用 libdet.h C API）：
   ```cpp
   #include "libdet.h"
   // 设备枚举 ...
   ax_det_init_t init_info = {};
   init_info.std[0] = 1.0f/255.0f; init_info.std[1] = 1.0f/255.0f; init_info.std[2] = 1.0f/255.0f;
   init_info.dev_type = axcl_device;
   init_info.model_type = ax_det_model_type_yolov8;
   sprintf(init_info.model_path, "model.axmodel");
   init_info.num_classes = 80;
   init_info.threshold = 0.25f;
   ax_det_handle_t handle;
   ax_det_init(&init_info, &handle);
   // 加载 cv::Mat bgr → cvtColor → ax_det_img_t，然后:
   ax_det(handle, &img, &result);
   ax_det_deinit(handle);
   ```
4. **模型类型枚举**（与 libdet.h 保持一致）：
   | YOLO 变体 | C 枚举值 |
   |-----------|---------|
   | YOLOv5 | `ax_det_model_type_yolov5` (0) |
   | YOLOv8 | `ax_det_model_type_yolov8` (1) |
   | YOLOv8-Pose | `ax_det_model_type_yolov8_pose` (2) |
   | YOLO11 | `ax_det_model_type_yolo11` (3) |
   | YOLO11-Pose | `ax_det_model_type_yolo11_pose` (4) |
5. **依赖**：libdet.axera 依赖 OpenCV 和 AX runtime（`axengine` 时链接 `libax_engine.so`/`libax_sys.so`，`axcl` 时链接 `libaxcl_rt.so`），必须在 README 中说明这些依赖的安装方法。
6. **交叉编译**：使用 BSP SDK 的 OpenCV 静态库时，需同时链接 3rdparty 依赖：`libzlib.a liblibpng.a liblibjpeg-turbo.a liblibopenjp2.a liblibtiff.a liblibwebp.a libtegra_hal.a libittnotify.a`，加 `-lpthread -ldl -latomic`。

## C++ SDK README.md

`TASK_DIR/sdk/cpp/README.md` 必须包含：

1. **文件说明**：列出 bin/、lib/、include/ 和源码目录的文件和用途。
2. **运行依赖**：板端运行时库（如 `/soc/lib/libax_engine.so`）和如何设置 `LD_LIBRARY_PATH`。
3. **用法**：
   - 直接运行预编译程序（如 `./bin/visdrone_detect model.axmodel image.jpg 0.25`）
   - 集成到自己的项目（`#include "libdet.h"`、API 调用示例、编译命令如 `g++ -I include -L lib -o app app.cpp -ldet -lpthread -ldl`）
4. **编译（如需）**：指向 GitHub 仓库源码链接，交叉编译依赖（BSP SDK、交叉编译器版本）。
5. **API 说明**：列出 `ax_det_init_t` 结构体字段、`ax_det()` 函数签名等。

## 验证

- Python import 成功。
- C++ cmake configure 成功。
- Python SDK README 覆盖环境安装、运行示例、API 说明。
- C++ SDK README 覆盖本地/交叉编译、上板运行、API 说明。
- 生成 `sdk/sdk_report.md`。

## STOP

缺失必要 runtime API 信息且无法生成可编译骨架时停止，要求用户提供 SDK 运行时路径或头文件。
