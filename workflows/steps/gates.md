# 关键 gate 与失败策略（yaml gates / failure_policy 段摘要）

## Gates

- `required_inputs`：SOURCE / TARGET_HARDWARE 缺失 → 问用户
- `model_route`：`magnetar.stages.llm.classify` 判定 route=llm / general；
  hybrid 组合模型需用户确认 LLM/AR 子模型拆分方案
- `pulsar2_available`：本地 PULSAR2_BIN / PULSAR2_IMAGE / PATH / hf-mirror 镜像任一可用 → COMPILE；
  全不可用 → blocked；LLM 路由额外要求 `pulsar2 llm_build2` 可用（Pulsar2 ≥ 6.0）
- `export_valid`：general 静态 shape + ORT 加载 + 对分通过 → TOOLCHAIN；
  llm 权重可推理 + llm_build.sh 生成；失败 → 换策略重试或问用户
- `accuracy_gate`：general cosine ≥ 0.99 → 通过；llm 逐层 cosine min ≥ 0.99 +
  有板时语义验证 → 通过；失败 → 查 issues/，无匹配 STOP 并提议 QAT（官方 QAT.axera）
- `llm_route_acceptance`：llm 模型目录完整（config.json/tokenizer/逐层/post axmodel）+
  compile_cosine.min ≥ 0.99 → SDK-GEN；缺文件或 cosine < 0.99 → 回退 COMPILE
- `package_validation`：README/setup.sh/run.sh/self_test 全过 → PUBLISH；失败修脚本重试 ≤3 次
- `publish_gate`：目标/仓库/凭据确认 + URL 可访问 + 无凭据泄漏 → 完成

## 失败策略（failure_policy）

- 默认 fail；总尝试上限 3 次
- 回退链：COMPILE 失败 → EXPORT；SIMULATE 工具失败 / accuracy 不达标 → COMPILE；
  PACKAGE 校验失败 → 修脚本重打包；PUBLISH 失败 → 修凭据重试（≤2）
- LLM 回退链：llm_build2 失败 → EXPORT（调参数/拆分）；逐层 cosine < 0.99 → COMPILE
  （s8→s4 / bf16→fp16 / 调 context）；均失败 → STOP 提议 QAT 或回退通用路径
- 需问用户：SOURCE/TARGET_HARDWARE 缺失、私有凭据、Pulsar2 不可用、仅有随机校准数据、
  hybrid 拆分方案、llm_build2 不支持架构时的回退方向、精度不达标无已知修复、
  板端凭据、多次导出失败、发布目标/仓库/凭据
- 可降级：C++ 交叉编译器缺失但 CMake configure 通过（degraded_output_allowed）
