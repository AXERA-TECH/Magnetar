---
name: allocate
description: Hidden stage for 7x24. Allocate idle AX boards from dashboard for parallel model conversion.
---

# ALLOCATE

从内网 dashboard 分配空闲 AX 板，每块板对应一个并行转换槽位。

## 步骤

1. 查询 dashboard 获取所有设备状态：

```bash
curl -s http://10.126.35.22:25000/api/devices | python3 -c "
import json, sys
devices = json.load(sys.stdin)
for d in devices:
    if d['status'] == 'idle' and d['chip'] in ('AX650', 'AX650N'):
        print(f\"{d['hostname']} {d['ip']} {d['chip']}\")
"
```

2. 按芯片型号分组，优先 AX650/AX650N。
3. 分配策略：
   - 最多 `MAX_CONCURRENT` 块板同时使用
   - 同一块板串行处理分配给它的模型队列
   - 分配后标记为 `allocated`（通过 dashboard API 或本地状态文件）
4. 写入 `7x24/boards.json`：

```json
{
  "boards": [
    {"ip": "10.168.232.116", "chip": "AX650N", "status": "allocated", "model": "visdrone-yolov11s"}
  ],
  "available": 2,
  "total": 3
}
```

## 释放

模型转换完成（成功或失败）后释放板端标记：

```bash
# 释放板端资源，清理 /tmp 下的临时文件
ssh root@<ip> "rm -rf /tmp/magnetar-*"
```

## STOP

- 无可用板时 STOP，等待下一轮。
- 连续 3 次无法分配时记录告警。

## 验证

- `boards.json` 中 `available + allocated = total`。
- 每块 allocated 板的 SSH 连通性验证通过。
