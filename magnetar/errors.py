"""类型化错误码：单一事实来源，供 retry_on / 状态机回退精确匹配。

约定：
- ``ERROR_CODES`` 与 ``workflows/magnetar.yaml`` 各步骤 ``retry.retry_on`` 对齐，
  由测试强制（tests/test_errors.py）；新增可重试错误码必须两处同步登记。
- stage 函数抛错统一用 ``MagnetarError(code, ...)``（或子类），外层（Agent /
  runner）用 ``classify_error`` 沿 cause 链提取稳定错误码，不再靠人肉匹配报错文本。
- ``BLOCK_CODES`` 是 STOP / 阻塞类错误码：不可重试，用于 gate 判定和事件日志路由。
"""
from __future__ import annotations

# 可重试错误码注册表：code -> 中文说明（必须与 magnetar.yaml 的 retry_on 一致）
ERROR_CODES: dict[str, str] = {
    # 网络 / 下载
    "network_timeout": "网络请求超时",
    "network_transient": "网络瞬时故障",
    "partial_download": "下载不完整，需要重新下载",
    "download_failed": "下载失败",
    "docker_pull_failed": "Pulsar2 Docker 镜像拉取失败",
    # 文件系统
    "filesystem_transient": "文件系统瞬时错误",
    # EXPORT
    "export_failed": "ONNX 导出失败（含全部降级路径）",
    "validation_mismatch": "导出/编译对分验证不匹配（cosine < 阈值）",
    "validation_failed": "验证失败",
    "compile_rollback": "编译失败需回退 EXPORT 调整导出策略",
    # COMPILE
    "compile_failed": "Pulsar2 编译失败",
    "pulsar2_transient": "Pulsar2 瞬时故障",
    # SIMULATE
    "simulation_transient": "仿真瞬时故障",
    "tool_error": "工具执行错误",
    # SDK-GEN
    "generation_error": "SDK 代码生成错误",
    # RUNONBOARD
    "ssh_transient": "SSH / 板端连接瞬时故障",
}

# STOP / 阻塞错误码（不可重试，对应 AGENTS.md 的 STOP 点）
BLOCK_CODES: dict[str, str] = {
    "missing_requirement": "必需输入缺失（SOURCE / TARGET_HARDWARE）",
    "blocked_hybrid_route": "hybrid 组合模型拆分方案待用户确认",
    "blocked_accuracy": "SIMULATE 精度不达标且已知修复已穷尽（提议 QAT）",
    "blocked_pulsar2": "Pulsar2 不可用",
    "blocked_credentials": "需要私有凭据",
    "blocked_publish": "PUBLISH 目标 / 仓库名 / 凭据待确认",
}

ALL_CODES: dict[str, str] = {**ERROR_CODES, **BLOCK_CODES}


class MagnetarError(RuntimeError):
    """带稳定错误码的异常。code 必须已登记在 ALL_CODES（fail loud，防拼写漂移）。"""

    def __init__(self, code: str, message: str = "", *, fatal: bool = True):
        if code not in ALL_CODES:
            raise ValueError(
                f"未登记的错误码 {code!r}；请先加入 magnetar.errors.ALL_CODES"
                f"（可重试码同时写入 workflows/magnetar.yaml 的 retry_on）"
            )
        super().__init__(message or code)
        self.code = code
        self.fatal = fatal

    def __str__(self) -> str:
        return f"[{self.code}] {super().__str__()}"


def classify_error(exc: BaseException | None) -> str | None:
    """沿 __cause__/__context__ 链提取第一个已登记错误码；无则返回 None。"""
    seen: set[int] = set()
    while exc is not None:
        if id(exc) in seen:
            break
        seen.add(id(exc))
        code = getattr(exc, "code", None)
        if code in ALL_CODES:
            return code
        exc = exc.__cause__ or exc.__context__
    return None
