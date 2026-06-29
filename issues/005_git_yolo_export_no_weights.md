# [005] git 仓库类模型 EXPORT 失败：仓库内无预训练权重

## 现象
```
git_yolov5n  → FAILED: no exportable model found in origin/
git_yolov8n  → FAILED: no exportable model found in origin/
```

## 根因
`git clone https://github.com/ultralytics/yolov5`（和 ultralytics）只克隆**源码**，
仓库里不含 `.pt` 权重文件。权重需运行时按需下载：
- yolov5: `python export.py --weights yolov5n.pt ...` 会自动从 release 下载 yolov5n.pt
- yolov8: `yolo export model=yolov8n.pt format=onnx ...` 同理自动下载

benchmark 脚本的 EXPORT 只检测 `origin/` 下已存在的模型文件，
没有执行 `models.yaml` 里提供的 `export_hint` 命令，所以找不到可导出文件。

## 解决方向
对 git 来源模型，EXPORT 应：
1. 读取 `models.yaml` 的 `export_hint` 字段。
2. 在 `origin/` 内安装依赖（`pip install -r requirements.txt` 或 `pip install ultralytics`）。
3. 执行 export_hint 命令（需联网下载权重，注意代理）。
4. 收集产出的 `.onnx` 到 `export/`。

注意：
- ultralytics 导出的 YOLO ONNX 默认含动态 batch 和后处理，pulsar2 需静态 shape，
  通常要 `--simplify` 并固定 imgsz。
- YOLO 的 Detect 头（含 sigmoid + grid）部分算子在 AX 上可能需替换，参见 issues/early_models.md。

## 复现
`bash todos/benchmark/run_one.sh git_yolov5n`

## 状态
未解决。benchmark 脚本未实现 git 来源的 export_hint 执行逻辑。
（注：axmodel-pipeline 设计文档 hidden/export/SKILL.md 已规划 git_export_py 策略，但 benchmark 脚本未实现。）
