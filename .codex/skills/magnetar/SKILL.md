---
name: magnetar
description: Convert remote or local AI models into AXera AXMODEL packages with Python and C++ SDKs for customer delivery.
---

# Magnetar

始终用中文沟通。完整工作流和爱芯开发知识见 `AGENTS.md`。

## 执行

按顺序推进 10 阶段，每阶段读取对应 `hidden/<stage>/SKILL.md`：

```
ACQUIRE → INIT → EXPORT → TOOLCHAIN → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE → PUBLISH
```

- 各阶段优先调用 `magnetar/stages/*.py` 工具函数
- 遇到 STOP 点暂停等用户确认
- BOARD 未配置时 RUNONBOARD 自动跳过
- 回退/重试/循环逻辑由 `workflows/magnetar.yaml` 状态机控制

## 阶段速查表

常规流程按下表推进；只有出现异常/STOP 时才深入读取对应 `hidden/<stage>/SKILL.md`，
正常路径不再逐个加载全部 hidden 技能以节省上下文。

**状态与进度一律读 `TASK_DIR/.magnetar-state.json`**（阶段/产物/一句话摘要），
不读 task.md 全文；task.md 仅作人类可读审计。

| 阶段 | 执行函数 | 验证要点 | STOP |
|------|----------|----------|------|
| INIT | `stages.init.run(config)` | 9 个子目录 + task.md/analysis.md/config.json | 无 |
| ACQUIRE | `stages.acquire.run(task_dir, source)` | origin/ 有文件 + ACQUIRE_REPORT.md | SOURCE 无效 / 私有凭据缺失 |
| EXPORT | `run_mobilenet` 或 `run_generic`（通用导出器） | 静态 ONNX + cosine≥0.99 + model_meta + 校准数据 | 对分失败 / 动态 shape 静态化失败 |
| TOOLCHAIN | `stages.toolchain.run()` | pulsar2 可用 + BSP 交叉编译器存在 | Pulsar2 / BSP 不可获取 |
| COMPILE | `stages.compile.run(task_dir, hw, image)` | axmodel 非空 + compile_report（MACs/大小/耗时） | 编译失败需改 ONNX → 退回 EXPORT |
| SIMULATE | `stages.simulate.run(...)`（优先板端） | cosine≥0.99 + 多样本均值±标准差 | 精度不达标 → 先查 `issues/INDEX.md` |
| SDK-GEN | `run_mobilenet_python/cpp` 或 `run_generic_python/cpp`（基于 model_meta + model_flow） | `import <sdk>` 通过 + cmake configure 通过 + 与 ACQUIRE 运行流程一致 | 无 |
| RUNONBOARD | `stages.runonboard.run(...)` | Python/C++ 板端 cosine≥0.98 + 延迟/内存 | 无（BOARD 缺失自动跳过） |
| PACKAGE | `stages.package.assemble` + `self_test` | self_test 通过 + README 无占位符 + 可独立发布 | 无 |
| PUBLISH | `stages.publish.publish(...)` | 返回 repo/model URL | 询问发布目标、仓库名、凭据 |

## Token 效率约定

- 大日志（compile.log、pulsar2_run.log、SSH 输出）只读尾部 `tail -100` 与关键指标，完整日志落盘不读入
- docker/SSH 大输出默认截断（`magnetar.docker_util.run` / `board_util.ssh` 的 max_tail），完整日志只落盘，异常只带尾部
- 编译后调用 `magnetar.stages.compile.summarize_compile_log(task_dir)` 取 MACs/大小/错误行，禁止读 compile.log 全文
- **禁止读取二进制产物**（.npy/.bin/.axmodel/.onnx/.pt 等）；需要 shape 用 numpy 查询，需要指标用摘要函数
- 查 `issues/` 先读 `issues/INDEX.md`，只读命中的文件
- 每阶段只用一句话结论更新 `task.md`/`analysis.md`，详细报告落盘
- 每阶段只读一次对应 hidden SKILL.md，不重复通读 `workflows/magnetar.yaml`
- 需求对齐先读 `.magnetarrc` 并探索仓库，缺失项一次性列清单带推荐答案确认
- 汇报/答复只给结论 + 指标，不贴大段日志
- 详细爱芯资源见 `docs/ax-knowledge.md`，按需读取

## 断点续跑

中断后恢复：新会话先读 `TASK_DIR/.magnetar-state.json`，从 `stage` 字段所在阶段继续；
只读当前阶段产物路径，不重放历史对话。`status=blocked` 时先看对应阶段报告/诊断再重试。

## 配置

读取 `.magnetarrc`（shell 风格 key=value），环境变量可覆盖。详见 `.magnetarrc.example`。
INIT 后各阶段读 `TASK_DIR/config.json`（`magnetar.config.load_task_config(task_dir)`），
任务参数以 INIT 快照为准，`.magnetarrc` 仅作公共默认，多任务并发互不影响。
