---
name: runonboard
description: Hidden stage for magnetar. Optionally deploy AXMODEL and SDK examples to an AX board and verify runtime behavior.
---

# RUNONBOARD

目标：在用户提供的 AX 开发板上验证 `model.axmodel` 和示例，并采集板端推理延迟和内存占用。

## 执行条件

必须执行。未提供 `BOARD` 时暂停并等待用户提供板端信息。

## 步骤

0. 根据 `AX_RUNTIME_TYPE` 选择验证策略：
   - `axcl`: 板端需有 `axcl_run_model` 和相关 AXCL 库；Python SDK 使用 pyaxengine（板端 axcl 兼容层）；C++ SDK 链接 `libaxcl_rt.so`。
   - `axengine`: 板端需有 `ax_run_model` 和相关 axengine 库（默认在 `/soc/lib/`）；Python SDK 使用 pyaxengine；C++ SDK 链接 `libax_engine.so`。


1. 解析 `BOARD`: `user@host[:port]`。
2. 确认 SSH 凭据可用；默认密码可使用用户提供的 `123456`，不得猜测其他密码或私钥。
3. 确认板端芯片类型与 `TARGET_HARDWARE` 匹配，例如 `TARGET_HARDWARE=AX650` 必须选择 `chip_type` 包含 `AX650` 的板子。
4. 推送：
   - `compile/model.axmodel`
   - 测试输入
   - Python SDK 示例
   - 主机交叉编译得到的 C++ SDK 二进制
5. 可选使用 `ax_run_model` 做 AXMODEL 格式和最小运行 smoke check；该命令不得替代 Python/C++ SDK 验证。
6. Python SDK 必须通过 `pyaxengine` 的 `AxEngineExecutionProvider` 运行；provider 不可用时才允许 fallback，并记录原因。
7. C++ SDK 必须在主机通过 aarch64 工具链交叉编译，板端只运行二进制；不得在板端编译。
8. C++ SDK 必须链接并调用 AX runtime（`axengine` 时链接 `libax_engine.so`/`libax_sys.so`，`axcl` 时链接 `libaxcl_rt.so`），不得调用 `ax_run_model` 或 `axcl_run_model`。
9. 拉回 Python/C++ 输出，与 SIMULATE 或 ONNX 输出对比；至少记录 shape、dtype、cosine、MAE。
10. **板端延迟测量**：
   - Python SDK：在板端用 `time python3 example.py ...` 或脚本内 `time.time()` 计时代码，记录单次推理耗时（ms）。
   - C++ SDK：在板端用 `time ./cpp_example ...` 记录单次推理耗时（ms）。
   - 可选：用 `time ax_run_model` 获取额外参考延迟。
11. **板端内存采集**（尝试获取，失败标 N/A）：
   - 系统内存：推理前执行 `free -m` 或读取 `/proc/meminfo`，记录可用内存；推理后再次执行，记录增量。
   - CMM 专用内存：推理前后各执行一次 `cat /proc/ax_proc/mem_cmm_info`，记录 CMM 占用和增量；路径不存在时标记 N/A。
12. 生成 `runonboard/runonboard_report.md`，含：
   - 精度对比（shape、dtype、cosine、MAE）
   - Python SDK 单次推理延迟（ms）
   - C++ SDK 单次推理延迟（ms）
   - 系统内存增量（MB）
   - CMM 占用信息或 N/A

## STOP

- 缺少 SSH 凭据。
- 找不到与 `TARGET_HARDWARE` 匹配的板子。
- 板端缺少运行时。
- Python SDK 或 C++ SDK 未能真实运行。
- 板端输出与仿真明显不一致。
