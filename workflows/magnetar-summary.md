# Magnetar 工作流摘要（日常按此执行，不用通读 yaml 全文）

> 权威状态机：`workflows/magnetar.yaml`（仅状态机诊断/排障时才读全文）。
> 日常执行：本摘要（全局只读一次）+ `workflows/steps/<阶段>.md`（每阶段只读对应片段）。

## 阶段顺序

`INIT → ACQUIRE → EXPORT → TOOLCHAIN → COMPILE → SIMULATE → SDK-GEN → RUNONBOARD → PACKAGE → PUBLISH`

| 阶段 | yaml 步骤 id | 片段 | hidden skill |
|------|--------------|------|--------------|
| INIT | `init` | steps/init.md | hidden/init |
| ACQUIRE | `acquire` | steps/acquire.md | hidden/acquire |
| EXPORT | `export` | steps/export.md | hidden/export |
| TOOLCHAIN | `toolchain` | steps/toolchain.md | hidden/toolchain |
| COMPILE | `compile` | steps/compile.md | hidden/compile |
| SIMULATE | `simulate` | steps/simulate.md | hidden/simulate |
| SDK-GEN | `sdk_gen` | steps/sdk-gen.md | hidden/sdk-gen |
| RUNONBOARD | `runonboard` | steps/runonboard.md | hidden/runonboard |
| PACKAGE | `package` | steps/package.md | hidden/package |
| PUBLISH | `publish` | steps/publish.md | hidden/publish |

## 关键 gate

- `requirements_gate`：SOURCE / TARGET_HARDWARE 必填；BOARD 可选（缺失跳过 RUNONBOARD）
- `dry_run_check`：MODE=dry-run 时展示计划即 STOP，需切 MODE=full
- `export_valid`：静态 shape + ORT 可加载 + Torch/ONNX 对分通过
- `accuracy_gate`：cosine ≥ 0.99；失败先查 `issues/`，无匹配 STOP 并提议 QAT
- `package_validation`：self_test 全过（README → setup.sh → run.sh），失败修脚本重试 ≤3 次
- `publish_gate`：目标/仓库名/凭据确认 + URL 可访问 + 无凭据泄漏

## STOP 点（等用户）

SOURCE/TARGET_HARDWARE 缺失、对分失败、动态 shape 静态化失败、Pulsar2 不可用、
编译失败需改 ONNX（回退 EXPORT）、SIMULATE 精度不达标无已知修复（先提议 QAT）、
私有凭据、PUBLISH 目标/仓库/凭据。

## 回退/重试

- COMPILE 失败 → 回退 EXPORT（调导出策略）
- SIMULATE 工具失败 / accuracy 不达标 → 回退 COMPILE（调量化配置）
- PACKAGE 校验失败 → 修脚本重打包，≤3 次
- PUBLISH 失败 → 修凭据/仓库重试，≤2 次
- 总尝试上限：3 次；超出转人工

## 常用输入（yaml inputs 段，环境变量可覆盖）

SOURCE、TARGET_HARDWARE、MODEL_NAME、TASK_DIR、HF_TOKEN、HF_ENDPOINT、
PULSAR2_IMAGE、PULSAR2_BIN、PULSAR2_HF_REPO、BOARD、BOARD_PASSWORD、
AUTO_APPROVE、MODE。

## 完成条件

requirement.acceptance 的 checks + required_artifacts 全过；RUNONBOARD 已尝试
（有板执行、无板跳过）；publish URL 与目标记录在 task.md。
