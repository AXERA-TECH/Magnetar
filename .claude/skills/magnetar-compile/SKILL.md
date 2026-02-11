---
description: Workflow COMPILE;
user-invocable: false
---

# Pulsar2

## 使用
文档说明: https://pulsar2-docs.readthedocs.io/zh-cn/latest/
参考json: templates/simple_pulsar2_config.json
禁止配置 "highest_mix_precision": true,
遇到精度问题，首先查看 `https://pulsar2-docs.readthedocs.io/zh-cn/latest/appendix/precision_debug_guides.html` 排查问题；


## 环境
```
source /home/xiguapro/workspace/cli_yaquantize/.venv/bin/activate
source /home/xiguapro/workspace/npu-codebase/script/npu_dev
```
