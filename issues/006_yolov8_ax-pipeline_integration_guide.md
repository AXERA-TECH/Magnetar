# YOLO-like 模型 ax-pipeline 集成指南

> 基于 yolov8 110cls 项目的实战经验总结。后续所有 YOLO 类模型交付必须参照此流程。

---

## 一、前提条件

- 已完成 Magnetar 全流程（ACQUIRE → PACKAGE）
- 模型已编译为 `.axmodel`，仿真验证通过
- 使用 `yolov8_split` 插件（split outputs: bbox + cls）

---

## 二、ax-pipeline 源码补丁（必须）

### 补丁 1：OSD 边界修复

**问题**：AX650 MSP 的 `AX_IVPS_DrawRect` 在矩形贴边（y=0）或接近画布满高时硬件失败，错误码 `0x800D020A`。

**修复** (`src/app/pipeline_instance.cpp`)：检测框内缩 1px。

```diff
- r.x = static_cast<std::int32_t>(x0f);
- r.y = static_cast<std::int32_t>(y0f);
- r.width = static_cast<std::uint32_t>(w);
- r.height = static_cast<std::uint32_t>(h);
+ r.x = static_cast<std::int32_t>(x0f) + 1;
+ r.y = static_cast<std::int32_t>(y0f) + 1;
+ r.width = static_cast<std::uint32_t>(w > 2 ? w - 2 : w);
+ r.height = static_cast<std::uint32_t>(h > 2 ? h - 2 : h);
```

共两处（tracker 分支和 dets 分支）。

### 补丁 2：osd_hold_frames 可配置

**文件**：`include/config_loader.hpp`

```diff
+ // osd_hold_frames: how many output frames the OSD overlay persists (default 10).
+ std::int32_t osd_hold_frames{10};

+ if (!GetOptI32(n, "osd_hold_frames", &out->npu.osd_hold_frames)) return false;
```

**文件**：`src/app/pipeline_instance.cpp`

```diff
- osd.hold_frames = 10;
+ osd.hold_frames = cfg_.npu.osd_hold_frames;
```

### 补丁文件

以上两个补丁已合并为单一 patch：

```
package/ax-pipeline-fixes.patch
```

应用到 ax-pipeline 源码：

```bash
cd ax-pipeline/
git apply ax-pipeline-fixes.patch
```

---

## 三、配置文件关键参数

### 必须设置

| 参数 | 值 | 原因 |
|------|-----|------|
| `realtime_playback` | **`true`** | mp4 文件必须！否则解码不限速，NPU 跟不上 |
| `npu_max_fps` | `0` | 不限速，让 NPU 每帧都跑 |

### 推荐设置

| 参数 | 值 | 说明 |
|------|-----|------|
| `osd_hold_frames` | `30` | 框持续帧数。5fps 时 30=6秒。小视频设大，RTSP 可设小 |
| `conf_threshold` | `0.2` | 可根据实际效果调整 |
| `nms_threshold` | `0.45` | NMS 去重 |

### 最小可用配置模板

```json
{
  "system": { "device_id": -1, "enable_vdec": true, "enable_venc": true, "enable_ivps": true, "vnpu_mode": "disable" },
  "pipelines": [{
    "name": "p0",
    "uri": "./test.mp4",
    "realtime_playback": true,
    "loop_playback": true,
    "npu_max_fps": 0,
    "frame_output": { "format": "bgr", "width": 640, "height": 640, "resize": { "mode": "keep_aspect", "horizontal_align": "center", "vertical_align": "center", "background_color": 0 } },
    "npu": {
      "enable": true,
      "enable_osd": true,
      "osd_hold_frames": 30,
      "ax_plugin_path": "./lib/plugins/libax_plugin_yolov8_split.so",
      "ax_plugin_isolation": "inproc",
      "ax_plugin_init_info": {
        "model_path": "./model.axmodel",
        "num_classes": <N>,
        "conf_threshold": 0.2,
        "nms_threshold": 0.45
      }
    },
    "outputs": [ { "codec": "h264", "uris": ["rtsp://0.0.0.0:8554/result"] } ]
  }]
}
```

---

## 四、部署包结构

每个模型交付时，`package/` 下必须包含：

```
package/
├── ax-pipeline-deploy/           # ← 开箱即用目录
│   ├── run.sh                    # 一键启动
│   ├── ax_pipeline_app           # 预编译主程序
│   ├── model.axmodel             # NPU 模型
│   ├── test.mp4                  # 测试视频
│   ├── config.json               # 配置文件
│   ├── README.md                 # 客户文档（含源码编译指南）
│   ├── lib/
│   │   ├── libax_video_sdk.so
│   │   └── plugins/
│   │       └── libax_plugin_yolov8_split.so
│   └── ax-pipeline-fixes.patch   # 源码补丁
└── ax-pipeline-deploy.tar.gz     # 打包
```

---

## 五、常见问题速查

| 现象 | 根因 | 修复 |
|------|------|------|
| 框一闪就没 | `realtime_playback: false` 导致全速解码 | 改 `true` |
| 框闪一下就消失 | `osd_hold_frames` 太小，NPU 跟不上 | 调大（30+） |
| pipeline osd: apply failed | AX650 硬件画框贴边失败 | 打边界修复补丁 |
| RTSP 拉不到流 | 板端防火墙/端口占用 | `netstat -tlnp` 检查 8554 |
| permission denied | sftp 上传未设执行权限 | `chmod +x ax_pipeline_app` |

---

## 六、生成测试视频

```bash
# 图片每张停留 5 秒，5fps 输出
ffmpeg -y -framerate 0.2 -pattern_type glob -i "*.jpg" \
  -vf "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2" \
  -r 5 -c:v libx264 -pix_fmt yuv420p -g 5 test.mp4
```

---

## 七、源码编译流程

```bash
git clone --recurse-submodules https://github.com/AXERA-TECH/ax-pipeline.git
cd ax-pipeline
git apply /path/to/ax-pipeline-fixes.patch
./build_ax650.sh
# 产物：artifacts/ax650/ax_pipeline_ax650.tar.gz
```

---

## 八、验证检查清单

- [ ] `realtime_playback: true`
- [ ] 已打边界修复补丁
- [ ] 配置文件含 `osd_hold_frames`
- [ ] NPU 覆盖率 > 70%（`npu_ok/decoded`）
- [ ] 零 `apply failed` 错误
- [ ] RTSP 流可在宿主机拉取
- [ ] 客户 README 含源码编译指南
- [ ] 部署包完整（二进制 + 模型 + 视频 + 配置 + 补丁）

---

*最后更新：2026-07-24，基于 yolov8 110cls AX650 实战*
