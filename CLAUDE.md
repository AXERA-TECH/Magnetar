# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 模型导出

默认使用 `source /home/xiguapro/workspace/cli_yaquantize/.venv/bin/activate` 
如果环境不满足，则需要使用 uv 重新安装环境


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

