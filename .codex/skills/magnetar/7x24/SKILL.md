---
name: magnetar-7x24
description: 7x24 autonomous model discovery → conversion → publish loop. Discovers trending models from HF/GitHub, runs full Magnetar pipeline, publishes successful conversions to HF and GitHub.
---

# Magnetar 7x24

持续运行的自主模型转换流水线。自动发现热门模型，执行完整 Magnetar 9 阶段转换，成功则发布到 HF 和 GitHub。

```
DISCOVER → FILTER → [ALLOCATE → MAGNETAR 9-STAGE → PUBLISH] × N
```

## 输入

- `MAX_CONCURRENT`: 最大并行模型数，默认 3（受限于可用板数）。
- `CYCLE_SLEEP_MINUTES`: 每轮发现间隔，默认 60 分钟。
- `MAX_MODELS_PER_CYCLE`: 每轮最多发现模型数，默认 5。
- `QUEUE_FILE`: 模型队列文件，默认 `7x24/queue.json`。
- `LOG_DIR`: 日志目录，默认 `7x24/logs/`。

## 调度循环

1. **DISCOVER**: 读取 [hidden/discover/SKILL.md](hidden/discover/SKILL.md)，从 HF/GitHub trending 抓取模型列表。
2. **FILTER**: 读取 [hidden/filter/SKILL.md](hidden/filter/SKILL.md)，排除 LLM（text-generation/conversational），去重已有记录。
3. **ALLOCATE**: 读取 [hidden/allocate/SKILL.md](hidden/allocate/SKILL.md)，从 dashboard 分配空闲 AX 板。
4. 对每个模型并行执行标准 Magnetar 9 阶段（ACQUIRE→PACKAGE）。
5. **PUBLISH**: 读取 [hidden/publish/SKILL.md](hidden/publish/SKILL.md)，板端验证通过后生成 SDK+model_convert 并推送 HF + GitHub。
6. 更新队列和日志，等待下一轮。

## STOP 点

- 无法从 dashboard 分配任何可用板。
- 连续 3 个模型编译失败（可能 Pulsar2 或环境异常）。
- 磁盘空间 < 10GB 或 Docker 不可用。
- HF/GitHub 推送连续失败超过 5 次。

## 日志

每轮生成两个日志：

- `7x24/logs/cycle-<timestamp>.md`: 本轮所有模型的完整记录
- `7x24/logs/summary.md`: 汇总统计（总计/成功/失败/跳过）

## 队列格式

`7x24/queue.json`:

```json
{
  "pending": [
    {"source": "hf:user/model", "name": "model-name", "task": "object-detection"},
    {"source": "gh:user/repo", "name": "model-name", "task": "image-classification"}
  ],
  "completed": [],
  "failed": [],
  "last_cycle": "2026-07-13T10:00:00Z"
}
```

## 与标准 Magnetar 的关系

7x24 不修改标准 9 阶段。每个模型的转换完全复用 `magnetar` skill。7x24 只负责：
- 从哪里获取模型
- 什么时候跑
- 跑完怎么发布
