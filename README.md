# Magnetar

将远程或本地的浮点 AI 模型一键转换为 AX 芯片可部署的 AXMODEL 交付包。

`模型 → ONNX → Pulsar2 编译 → AXMODEL → 仿真 → Python/C++ SDK → 交付包`

## 安装

```bash
git clone https://github.com/AXERA-TECH/Magnetar.git
cd Magnetar
./setup.sh
```

需要 Docker 和 Pulsar2，一键安装：

```bash
./scripts/install_pulsar2.sh
```

## 使用

在 Codex 中直接说：

```
使用 magnetar，把 SOURCE=<模型路径/URL> 转换到 AX650
```

或手动执行：

| 阶段 | 说明 |
|------|------|
| ACQUIRE | 获取模型权重 |
| EXPORT | 导出静态 ONNX |
| COMPILE | Pulsar2 编译 AXMODEL |
| SIMULATE | 仿真对比精度 |
| SDK-GEN | 生成 Python/C++ SDK |
| RUNONBOARD | 板端验证 |
| PACKAGE | 打包交付 |

## 交付物

```
package/
  models/          AXMODEL
  python/          Python SDK
  cpp/             C++ SDK
  model_convert/   复现脚本 & 配置
```

默认输出到 `todos/work/<timestamp>-<model>/package/`。

## 工具链

- **Pulsar2**: [hf-mirror.com/AXERA-TECH/Pulsar2](https://hf-mirror.com/AXERA-TECH/Pulsar2)
- **pyaxengine**: [github.com/AXERA-TECH/pyaxengine](https://github.com/AXERA-TECH/pyaxengine)
- **libdet.axera**: [github.com/AXERA-TECH/libdet.axera](https://github.com/AXERA-TECH/libdet.axera) (YOLO 后处理)
- **BSP SDK**: [hf-mirror.com/AXERA-TECH/AX650-Community-Hub](https://hf-mirror.com/AXERA-TECH/AX650-Community-Hub)

Python 虚拟环境统一用 `uv`，HuggingFace 下载统一走 `hf-mirror`。

## 测试

```bash
python -m unittest discover -s tests
```

常用环境变量：

| 变量 | 默认值 |
|------|--------|
| `MAGNETAR_TARGET_HARDWARE` | AX650 |
| `MAGNETAR_BOARD` | 自动选择空闲板 |
| `MAGNETAR_BOARD_PASSWORD` | 123456 |
