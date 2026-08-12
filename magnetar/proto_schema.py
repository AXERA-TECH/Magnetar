"""Pulsar2 编译配置 schema——字段级校验的权威来源。

数据来源只取 Pulsar2 镜像内的 ``build_config.proto`` / ``common.proto``
（客户侧工具链产物，已由 ``magnetar.docker_util.extract_pulsar2_proto``
缓存到本地），不依赖也不复制工具链内部源码。

用法::

    from magnetar.proto_schema import load_schema
    schema = load_schema("pulsar2:7.0")
    errors = schema.validate(config)   # list[str]，空列表 = 通过

与 ``magnetar/pulsar2_ref.py::validate_config`` 的区别：
后者做业务规则校验（U8 std=255、weight_data_type、三选一等），
本模块做 proto 字段级校验（未知字段/类型/枚举成员/必填字段/默认值提示）。
两者配合使用：先字段级，再业务级。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── proto 文本解析 ───

_ENUM_OPEN_RE = re.compile(r"^enum\s+(\w+)\s*\{")
_MESSAGE_OPEN_RE = re.compile(r"^message\s+(\w+)\s*\{")
_FIELD_RE = re.compile(
    r"^\s*(?:(repeated|optional)\s+)?([A-Za-z_][\w.]*)\s+(\w+)\s*=\s*(\d+)\s*;"
)
_ENUM_MEMBER_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(-?\d+)\s*;")
_META_RE = {
    "required": re.compile(r"required:\s*(\w+)"),
    "default": re.compile(r"default:\s*([^.;]+?)\s*(?:\.\s|\.$|$)"),
    "option": re.compile(r"option:\s*([^.;]+?)\s*(?:\.\s|\.$|$)"),
    "limitation": re.compile(r"limitation:\s*([^.;]+?)\s*(?:\.\s|\.$|$)"),
}


@dataclass
class FieldDef:
    """proto message 中一个字段的定义。"""

    name: str
    number: int
    proto_type: str
    repeated: bool = False
    optional: bool = False
    meta: dict[str, str] = field(default_factory=dict)
    comment: str = ""


@dataclass
class Schema:
    """Pulsar2 proto 的枚举 + message 结构。"""

    enums: dict[str, dict[str, int]] = field(default_factory=dict)
    messages: dict[str, dict[str, FieldDef]] = field(default_factory=dict)

    # ── 字段级校验 ──

    def validate(self, config: Any, root: str = "BuildConfig") -> list[str]:
        """校验配置字典，返回错误列表（空列表 = 通过）。"""
        errors: list[str] = []
        self._validate_message(root, config, errors, "")
        return errors

    def _validate_message(
        self, msg_name: str, value: Any, errors: list[str], prefix: str
    ) -> None:
        if not isinstance(value, dict):
            errors.append(f"{prefix or msg_name}: 期望对象，实际 {type(value).__name__}")
            return
        fields = self.messages.get(msg_name)
        if fields is None:
            # 未解析的 message（如 isp.ISPConfig / google.protobuf.Struct），
            # 不做深层校验，避免误报。
            return
        for key, val in value.items():
            f = fields.get(key)
            path = f"{prefix}.{key}" if prefix else key
            if f is None:
                known = ", ".join(sorted(fields)[:20])
                errors.append(f"{path}: 未知字段（可选项: {known}）")
                continue
            self._validate_field(f, val, path, errors)
        for f in fields.values():
            if f.meta.get("required") == "true" and f.name not in value:
                path = f"{prefix}.{f.name}" if prefix else f.name
                errors.append(f"{path}: 必填字段缺失")

    def _validate_field(
        self, f: FieldDef, value: Any, path: str, errors: list[str]
    ) -> None:
        if f.repeated:
            if not isinstance(value, list):
                errors.append(f"{path}: 期望数组，实际 {type(value).__name__}")
                return
            for i, item in enumerate(value):
                self._validate_value(f, item, f"{path}[{i}]", errors)
            return
        self._validate_value(f, value, path, errors)

    def _validate_value(
        self, f: FieldDef, value: Any, path: str, errors: list[str]
    ) -> None:
        t = f.proto_type
        base = t.split(".")[-1]

        if base in self.messages:
            self._validate_message(base, value, errors, path)
            return
        if base in self.enums:
            members = self.enums[base]
            if not isinstance(value, str) or value not in members:
                valid = ", ".join(members)
                errors.append(
                    f"{path}: 枚举值 '{value}' 不在 {base} 中（可选: {valid}）"
                )
            return
        if t in ("string",):
            if not isinstance(value, str):
                errors.append(f"{path}: 期望字符串，实际 {type(value).__name__}")
        elif t in ("bool",):
            if not isinstance(value, bool):
                errors.append(f"{path}: 期望布尔，实际 {type(value).__name__}")
        elif t in (
            "int32", "int64", "uint32", "uint64",
            "sint32", "sint64", "fixed32", "fixed64", "sfixed32", "sfixed64",
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"{path}: 期望整数，实际 {type(value).__name__}")
        elif t in ("float", "double"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{path}: 期望数值，实际 {type(value).__name__}")
        elif t in ("bytes",):
            if not isinstance(value, (str, bytes)):
                errors.append(f"{path}: 期望 bytes/base64，实际 {type(value).__name__}")
        # 其他未识别类型：跳过，避免误报


def parse_proto_files(paths: list[Path]) -> Schema:
    """解析一个或多个 proto 文件，合并 enum/message 定义。"""
    schema = Schema()
    for path in paths:
        _parse_proto_text(path.read_text(encoding="utf-8"), schema)
    return schema


def _parse_proto_text(text: str, schema: Schema) -> None:
    """单文件解析：enum → schema.enums，message → schema.messages。"""
    stack: list[str] = []  # 当前嵌套的 enum/message 名
    pending_comments: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            pending_comments.append(stripped[2:].strip())
            continue
        m = _ENUM_OPEN_RE.match(stripped)
        if m:
            stack.append(m.group(1))
            schema.enums.setdefault(m.group(1), {})
            pending_comments = []
            continue
        m = _MESSAGE_OPEN_RE.match(stripped)
        if m:
            stack.append(m.group(1))
            schema.messages.setdefault(m.group(1), {})
            pending_comments = []
            continue
        if stripped == "}":
            if stack:
                stack.pop()
            pending_comments = []
            continue
        if not stack:
            pending_comments = []
            continue
        if stack[-1] in schema.enums:
            # enum 成员：NAME = N;
            m = _ENUM_MEMBER_RE.match(stripped)
            if m:
                schema.enums[stack[-1]][m.group(1)] = int(m.group(2))
            pending_comments = []
            continue
        m = _FIELD_RE.match(stripped)
        if not m:
            continue
        if stack[-1] not in schema.messages:
            continue
        comment = " ".join(pending_comments)
        meta = {}
        for key, rx in _META_RE.items():
            mm = rx.search(comment)
            if mm:
                meta[key] = mm.group(1).strip()
        schema.messages[stack[-1]][m.group(3)] = FieldDef(
            name=m.group(3),
            number=int(m.group(4)),
            proto_type=m.group(2),
            repeated=(m.group(1) == "repeated"),
            optional=(m.group(1) == "optional"),
            meta=meta,
            comment=comment,
        )
        pending_comments = []


def load_schema(handle: str) -> Schema:
    """加载指定 Pulsar2 后端的 schema（pkg:<home> / img:<image>，裸字符串按镜像兼容）。"""
    from magnetar.docker_util import extract_pulsar2_proto

    files = extract_pulsar2_proto(handle)
    return parse_proto_files([files["common.proto"], files["build_config.proto"]])


# ─── input_shapes 解析 ───

_INPUT_SHAPES_RE = re.compile(r"([A-Za-z_][\w.]*):(\d+(?:x\d+)*)")


def parse_input_shapes_str(s: str) -> dict[str, list[int]]:
    """解析 ``input_shapes`` 字符串（如 ``input:1x3x224x224;mask:1x512``）。"""
    result: dict[str, list[int]] = {}
    for m in _INPUT_SHAPES_RE.finditer(s or ""):
        result[m.group(1)] = [int(x) for x in m.group(2).split("x")]
    return result
