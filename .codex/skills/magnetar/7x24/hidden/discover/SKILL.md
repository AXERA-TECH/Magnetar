---
name: discover
description: Hidden stage for 7x24. Discover trending models from HuggingFace and GitHub.
---

# DISCOVER

从 HF 和 GitHub 抓取热门模型，合并去重后写入队列。

## HF Trending

调用 HuggingFace API `/api/models?sort=downloads&direction=-1&limit=20`，过滤条件：

- pipeline_tag 不为 `text-generation` 或 `conversational`
- downloads > 100
- 模型大小 < 2GB（避免超大模型 OOM）

```python
import requests, os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

resp = requests.get("https://hf-mirror.com/api/models", params={
    "sort": "downloads", "direction": "-1", "limit": 20,
    "filter": "pipeline_tag:object-detection,pipeline_tag:image-classification,pipeline_tag:image-segmentation",
})
models = resp.json()
```

## GitHub Trending

调用 GitHub Search API `/search/repositories?q=topic:deep-learning+stars:>10&sort=stars`：

```bash
gh search repos --topic deep-learning --sort stars --limit 10 --json name,url,description,topics
```

从 README 或 repo 描述中提取模型名称和 HF 对应地址。

## 去重与入队

1. 与 `queue.json` 中 `completed` 和 `failed` 对比，跳过已处理过的。
2. 与 `pending` 对比，已在队列中的不重复添加。
3. 新模型添加到 `pending` 列表末尾，写入 `queue.json`。
4. 记录本轮发现的模型数量和来源到日志。

## 验证

- `queue.json` 中 `pending` 列表非空。
- 每个条目至少含 `source` 和 `task` 字段。
- 日志记录本轮发现数量和去重跳过的数量。
