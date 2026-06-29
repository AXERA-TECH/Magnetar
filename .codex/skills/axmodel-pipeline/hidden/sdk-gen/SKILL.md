---
name: sdk-gen
description: 基于model_meta.json为axmodel生成Python和C++推理SDK
type: hidden
---

# SDK-Gen

## 输入
- `model_meta`: `export/model_meta.json`（I/O名称、shape、dtype）
- `axmodel_path`: 编译产物路径
- `MODEL_NAME`: 用于命名类和文件
- `TARGET_HARDWARE`: AX650 | AX620E
- `SDK_LANG`: python | cpp | both

`model_meta.json` 结构示例：
```json
{
  "inputs":  [{"name": "images", "shape": [1,3,640,640], "dtype": "float32"}],
  "outputs": [{"name": "output0", "shape": [1,25200,85], "dtype": "float32"}]
}
```

## Python SDK 生成

输出目录：`TASK_DIR/sdk/python/{model_name}_sdk/`

文件：
```
{model_name}_sdk/
  __init__.py
  inference.py    # 核心推理类
  example.py      # 使用示例
  README.md
```

`inference.py` 模板（根据model_meta填充具体shape和tensor名）：
```python
import numpy as np
import axengine as axe   # AX SDK Python绑定

class {ModelName}Inference:
    def __init__(self, model_path: str = "{axmodel_filename}"):
        self._session = axe.InferenceSession(model_path)

    def run(self, {input_args}) -> {output_type}:
        """
        inputs: {input_meta}
        outputs: {output_meta}
        """
        outputs = self._session.run(
            None,
            { {input_feed} }
        )
        return outputs[0] if len(outputs) == 1 else outputs
```

如果 `axengine` 不可用（import失败），回退到注释形式，标注 `# requires axengine`，并在README说明安装方式。

## C++ SDK 生成

输出目录：`TASK_DIR/sdk/cpp/`

文件：
```
cpp/
  include/
    {model_name}_inference.h
  src/
    {model_name}_inference.cpp
  example/
    main.cpp
  CMakeLists.txt
  README.md
```

`{model_name}_inference.h` 模板（根据model_meta填充）：
```cpp
#pragma once
#include <vector>
#include <string>
#include "ax_engine.h"   // AX Engine C API

class {ModelName}Inference {
public:
    explicit {ModelName}Inference(const std::string& model_path);
    ~{ModelName}Inference();

    // input shape: {input_shape}  dtype: {input_dtype}
    // output shape: {output_shape}
    std::vector<float> run(const std::vector<float>& input);

private:
    AX_ENGINE_HANDLE handle_ = nullptr;
    AX_ENGINE_IO_T io_ = {};
};
```

`CMakeLists.txt` 模板（支持交叉编译）：
```cmake
cmake_minimum_required(VERSION 3.16)
project({model_name}_sdk)

# 交叉编译：cmake -DCMAKE_TOOLCHAIN_FILE=toolchain-aarch64.cmake ..
# 或直接：cmake -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc \
#              -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ ..

set(AXENGINE_ROOT "" CACHE PATH "AXEngine SDK根目录（含include/和lib/）")

add_library({model_name}_inference STATIC
    src/{model_name}_inference.cpp)
target_include_directories({model_name}_inference PUBLIC
    include
    $<$<BOOL:${AXENGINE_ROOT}>:${AXENGINE_ROOT}/include>)
if(AXENGINE_ROOT)
    target_link_libraries({model_name}_inference
        ${AXENGINE_ROOT}/lib/libax_engine.so)
endif()

add_executable({model_name}_example example/main.cpp)
target_link_libraries({model_name}_example {model_name}_inference)
```

额外生成 `toolchain-aarch64.cmake`（放在 `sdk/cpp/`）：
```cmake
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER   aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
```

## 验证

Python SDK：
```bash
python -c "from {model_name}_sdk import {ModelName}Inference; print('OK')"
```
失败时：检查语法错误，最多重试2次，之后降级（degrade）仅输出不可import的代码文件。

C++ SDK 交叉编译验证（按优先级）：
```bash
# 1. 用户提供 TOOLCHAIN_FILE
cmake -S sdk/cpp -B sdk/cpp/build \
    -DCMAKE_TOOLCHAIN_FILE={TOOLCHAIN_FILE} \
    -DCMAKE_BUILD_TYPE=Release && cmake --build sdk/cpp/build

# 2. 自动检测 aarch64-linux-gnu-g++
aarch64-linux-gnu-g++ --version 2>/dev/null && \
cmake -S sdk/cpp -B sdk/cpp/build \
    -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ \
    -DCMAKE_BUILD_TYPE=Release && cmake --build sdk/cpp/build

# 3. 降级：仅验证 cmake configure（不链接）
cmake -S sdk/cpp -B sdk/cpp/build -DCMAKE_BUILD_TYPE=Release
```
只要能通过 configure 阶段即视为SDK结构有效。实际链接依赖用户的AXEngine SDK包，在README中说明。

## 错误处理
| 错误 | 动作 |
|------|------|
| model_meta.json缺失 | fail，提示重新运行EXPORT |
| axengine不可用 | degrade：生成带注释的SDK，README说明依赖 |
| 无aarch64工具链 | degrade：跳过编译验证，生成源码+构建说明 |
| 模型名含特殊字符 | 自动sanitize为合法标识符 |
