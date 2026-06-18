# Magnetar

Pulsar2 Agent 工作流，目标是帮助用户完成：

`开源或自研模型 -> ONNX -> Pulsar2 编译 -> AXMODEL -> 仿真验证 -> 板端运行`

仓库同时保留 Claude 版工作流，并新增 Codex 版工作流。

# 快速开始

## Codex

本仓库提供项目级 Codex 规则和可复用 skill：

- `AGENTS.md`: Codex 进入本仓库后的默认约束。
- `.codex/skills/magnetar-deploy/SKILL.md`: Magnetar 部署工作流。

在 Codex 中可以直接说：

```text
使用 magnetar-deploy，把 repo=[本地路径或 git repo] 部署到 AX650，task_dir=[工作目录]
```

如需让 Codex 在其他仓库也自动发现该 skill，可将 `.codex/skills/magnetar-deploy` 复制或链接到 `${CODEX_HOME:-~/.codex}/skills/`。

## Claude

In Claude console:

```text
/magnetar repo=[本地路径或git repo] task_dir=[工作目录, 默认为claude的临时目录]
```
