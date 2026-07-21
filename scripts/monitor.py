#!/usr/bin/env python3
"""Magnetar 工作流 TUI 监控面板。

权威状态来源：TASK_DIR/task.md 中的"阶段状态"表格。
artifact 仅用于补充详情（文件大小、精度指标等）。

用法:
    python3 scripts/monitor.py <TASK_DIR>
    python3 scripts/monitor.py todos/work/20260720-mymodel/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import sys
import termios
import time
import tty
from datetime import datetime

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich import box

STAGES = [
    ("ACQUIRE",   "获取模型"),
    ("INIT",      "初始化工作目录"),
    ("EXPORT",    "导出静态ONNX"),
    ("TOOLCHAIN", "准备编译工具链"),
    ("COMPILE",   "Pulsar2 编译"),
    ("SIMULATE",  "仿真精度对分"),
    ("SDK-GEN",   "生成 Python/C++ SDK"),
    ("RUNONBOARD","板端验证"),
    ("PACKAGE",   "打包客户交付包"),
]

console = Console()

# ─── task.md 阶段状态表解析 ────────────────────────────

def parse_task_md(task_dir: str) -> dict[str, str]:
    """从 task.md 的阶段状态表格中提取每个阶段的状态。

    返回 {'ACQUIRE': 'completed', 'INIT': 'running', ...}
    只返回在表格中有明确状态值的阶段，不在表中的不返回。
    找不到 task.md 或表格时返回空 dict。
    """
    task_md = os.path.join(task_dir, "task.md")
    if not os.path.isfile(task_md):
        return {}

    with open(task_md) as f:
        lines = f.readlines()

    # 找到最后一个"阶段状态"所在行（task.md 可能有多张表，最后一张是最新状态）
    table_start = None
    for i, line in enumerate(lines):
        if "阶段状态" in line:
            table_start = i  # keep overwriting to get the last one
    if table_start is None:
        return {}

    # 从 table_start 之后找第一个 markdown 表格行（以 | 开头）
    header_line = None
    for j in range(table_start + 1, min(table_start + 8, len(lines))):
        stripped = lines[j].strip()
        if stripped.startswith("|") and "阶段" in stripped:
            header_line = j
            break
    if header_line is None:
        # 没有表格头 — 可能是空表格（如 parking-lot-yolo26m）
        return {}

    # 解析表头：确定"状态"列在第几列
    header_cells = [c.strip() for c in lines[header_line].split("|")]
    # header 形如 ['', '阶段', '状态', '开始时间', '完成时间', '']
    # 找到"状态"列索引（1-based from split）
    status_col = None
    for ci, cell in enumerate(header_cells):
        if "状态" in cell:
            status_col = ci
            break
    if status_col is None:
        return {}

    result: dict[str, str] = {}
    for j in range(header_line + 1, len(lines)):
        stripped = lines[j].strip()
        if not stripped.startswith("|"):
            break  # 表格结束
        # 跳过分隔线（|------|）
        if re.match(r'^\|[\s\-:]+\|', stripped):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # cells 形如 ['', 'ACQUIRE', '✅ 完成', '18:19', '18:34', '']
        if len(cells) < status_col + 1:
            continue
        stage_name = cells[1]
        status_raw = cells[status_col]

        # 匹配已知的阶段名
        matched = None
        for sn, _ in STAGES:
            if sn.upper() in stage_name.upper():
                matched = sn
                break
        if matched is None:
            continue

        parsed = _classify_status(status_raw)
        if parsed:
            result[matched] = parsed

    return result


def _classify_status(text: str) -> str | None:
    """将 task.md 中任意格式的状态文本映射为 'completed'/'running'/'pending'/'skipped'/'partial'。

    已知格式：
    - "✅ 完成" / "完成" / "✅" → completed
    - "🔄 进行中" / "进行中" → running
    - "⏳ 待执行" / "⬜ 待执行" / "待执行" / "⏳" / "⬜" → pending
    - "⚠️" / "部分完成" → partial（部分完成或有已知问题）
    - "N/A" / "跳过" / "−" → skipped
    """
    t = text.strip().lower()

    # completed: Chinese text or solo ✅
    if any(k in t for k in ["完成", "completed", "pass", "✅"]):
        return "completed"
    # running: 🔄 + 进行中 combo, or "running" text
    if any(k in t for k in ["进行中", "🔄"]):
        return "running"
    # partial: ⚠️ = completed with known issues
    if "⚠" in t:
        return "partial"
    # skipped: N/A, 跳过
    if any(k in t for k in ["n/a", "跳过", "skipped"]):
        return "skipped"
    # pending: 待执行 text, or solo ⏳ / ⬜ emoji
    if any(k in t for k in ["待执行", "pending", "⏳", "⬜"]):
        return "pending"
    # solo − (dash)
    if t.strip() == "−" or t.strip() == "-":
        return "skipped"

    return None


# ─── artifact 详情读取（辅助，不影响状态判定）────────────

def _file_size_mb(path: str) -> str:
    if os.path.isfile(path):
        return f"{os.path.getsize(path)/1024/1024:.1f} MB"
    return ""

def _file_size_kb(path: str) -> str:
    if os.path.isfile(path):
        return f"{os.path.getsize(path)/1024:.0f} KB"
    return ""

def _grep_first(path: str, pattern: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        for line in f:
            m = re.search(pattern, line)
            if m:
                return m.group(1)
    return None

def _get_detail(task_dir: str, stage_name: str) -> str:
    """根据阶段名从 artifact 中提取人类可读的详情字符串。"""
    if stage_name == "ACQUIRE":
        manifest = os.path.join(task_dir, "cache/acquire/manifest.json")
        if os.path.isfile(manifest):
            try:
                with open(manifest) as f:
                    data = json.load(f)
                src = data.get("source", "")
                if len(src) > 42:
                    src = src[:39] + "..."
                return f"来源: {src}" if src else ""
            except Exception:
                pass
        return ""

    if stage_name == "EXPORT":
        onnx = os.path.join(task_dir, "export/model.onnx")
        return f"ONNX: {_file_size_mb(onnx)}" if os.path.isfile(onnx) else ""

    if stage_name == "TOOLCHAIN":
        # Pulsar2 状态
        cmake = os.path.join(task_dir, "sdk/cpp/toolchain-aarch64.cmake")
        return "工具链就绪" if os.path.isfile(cmake) else ""

    if stage_name == "COMPILE":
        axmodel = os.path.join(task_dir, "compile/model.axmodel")
        report = os.path.join(task_dir, "compile/compile_report.md")
        parts = []
        if os.path.isfile(axmodel):
            parts.append(f"AXMODEL: {_file_size_kb(axmodel)}")
        m = _grep_first(report, r"MACs.*?(\d+\.?\d*)\s*G")
        if m:
            parts.append(f"MACs: {m} G")
        return " / ".join(parts) if parts else ""

    if stage_name == "SIMULATE":
        report = os.path.join(task_dir, "simulate/simulate_report.md")
        m = _grep_first(report, r"cosine.*?(\d+\.\d+)")
        return f"cosine: {m}" if m else ""

    if stage_name == "SDK-GEN":
        return "Python/C++ SDK 已生成"

    if stage_name == "RUNONBOARD":
        report = os.path.join(task_dir, "runonboard/runonboard_report.md")
        m = _grep_first(report, r"(Python|C\+\+).*?(\d+\.?\d*)\s*ms")
        return f"延迟: {m} ms" if m else "板端验证完成"

    if stage_name == "PACKAGE":
        pkg_dir = os.path.join(task_dir, "package")
        if os.path.isdir(pkg_dir):
            count = sum(len(files) for _, _, files in os.walk(pkg_dir))
            return f"交付包: {count} 个文件"
        return ""

    return ""


# ─── 主状态聚合 ─────────────────────────────────────

def get_stage_statuses(task_dir: str) -> list[tuple[str, str, str, str]]:
    """返回 [(stage_name, stage_desc, status, detail), ...]。

    status ∈ {'completed', 'running', 'pending', 'skipped'}
    权威来源: task.md 阶段状态表 > artifact 存在性 > 默认 pending
    """
    md_statuses = parse_task_md(task_dir)

    results = []
    for stage_name, stage_desc in STAGES:
        # 1. task.md 有明确状态 → 以此为准
        if stage_name in md_statuses:
            status = md_statuses[stage_name]
        else:
            # 2. task.md 无该阶段 → 根据 artifact 推断（只判 completed，不判 running）
            status = _infer_completed(task_dir, stage_name)

        # 3. detail 总是从 artifact 读取
        detail = _get_detail(task_dir, stage_name) if status in ("completed", "running") else ""

        results.append((stage_name, stage_desc, status, detail))

    return results


def _infer_completed(task_dir: str, stage_name: str) -> str:
    """当 task.md 无此阶段信息时，根据 artifact 推断是否已完成。

    策略保守：只判 completed，不判 running。避免误报进行中。
    因为 artifact 在阶段开始前可能就存在（重跑残留），不排除误判已完成。
    但有 task.md 的任务不会走到这里。
    """
    checks = {
        "ACQUIRE":    "cache/acquire/manifest.json",
        "EXPORT":     "export/model.onnx",
        "COMPILE":    "compile/model.axmodel",
        "SIMULATE":   "simulate/simulate_report.md",
        "SDK-GEN":    "sdk/sdk_report.md",
        "RUNONBOARD": "runonboard/runonboard_report.md",
        "PACKAGE":    "package/README.md",
    }
    if stage_name in checks:
        path = os.path.join(task_dir, checks[stage_name])
        return "completed" if os.path.isfile(path) and os.path.getsize(path) > 0 else "pending"
    return "pending"


# ─── Rich 布局 ──────────────────────────────────────

def build_layout(task_dir: str) -> Layout:
    task_name = os.path.basename(task_dir.rstrip("/"))
    statuses = get_stage_statuses(task_dir)

    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["header"].update(Panel(
        Text(f"  Magnetar Pipeline — {task_name}", style="bold cyan"),
        box=box.ROUNDED,
    ))

    layout["body"].split_row(
        Layout(name="stages", ratio=2),
        Layout(name="metrics", ratio=1),
    )
    layout["stages"].update(Panel(
        _build_stages_table(statuses),
        title="流水线阶段",
        border_style="blue",
    ))
    layout["metrics"].update(Panel(
        _build_metrics_table(task_dir, statuses),
        title="关键指标",
        border_style="green",
    ))

    footer_text = Text(
        f"  刷新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  "
        f"按 Ctrl+C 退出  |  "
        f"状态来源: {'task.md' if os.path.isfile(os.path.join(task_dir, 'task.md')) else 'artifact 推测'}  "
        f"|  TASK_DIR: {task_dir}",
        style="dim",
    )
    layout["footer"].update(Panel(footer_text, box=box.ROUNDED))

    return layout


def _build_stages_table(statuses: list) -> Table:
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("#", width=2, style="dim")
    table.add_column("阶段", width=12)
    table.add_column("状态", width=10)
    table.add_column("详情", width=30)

    icons_color = {
        "completed": ("✓", "green"),
        "running":   ("●", "yellow"),
        "pending":   ("○", "dim"),
        "skipped":   ("−", "dim"),
        "partial":   ("⚠", "yellow"),
    }
    labels = {
        "completed": "完成",
        "running":   "进行中",
        "pending":   "等待",
        "skipped":   "跳过",
        "partial":   "部分",
    }

    for i, (name, _desc, status, detail) in enumerate(statuses, 1):
        icon, color = icons_color.get(status, ("?", "dim"))
        label = labels.get(status, status)
        table.add_row(
            str(i),
            name,
            f"[{color}]{icon} {label}[/{color}]",
            f"[{color}]{detail}[/{color}]" if detail else "",
        )
    return table


def _build_metrics_table(task_dir: str, statuses: list) -> Table:
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    table.add_column("指标", style="dim")
    table.add_column("值", style="bold")

    task_name = os.path.basename(task_dir.rstrip("/"))
    table.add_row("任务", task_name)

    stage_status = {sn: st for sn, _, st, _ in statuses}

    def ok(sn): return stage_status.get(sn) == "completed"

    if ok("EXPORT"):
        p = os.path.join(task_dir, "export/model.onnx")
        if os.path.isfile(p):
            table.add_row("ONNX", f"{os.path.getsize(p)/1024/1024:.1f} MB")

    if ok("COMPILE"):
        ap = os.path.join(task_dir, "compile/model.axmodel")
        onp = os.path.join(task_dir, "export/model.onnx")
        if os.path.isfile(ap):
            table.add_row("AXMODEL", f"{os.path.getsize(ap)/1024:.0f} KB")
        if os.path.isfile(onp) and os.path.isfile(ap):
            r = os.path.getsize(onp) / max(os.path.getsize(ap), 1)
            table.add_row("压缩比", f"{r:.1f}:1")
        m = _grep_first(os.path.join(task_dir, "compile/compile_report.md"), r"MACs.*?(\d+\.?\d*)\s*G")
        if m:
            table.add_row("MACs", f"{m} G")

    if ok("SIMULATE"):
        table.add_row("cosine", _grep_first(
            os.path.join(task_dir, "simulate/simulate_report.md"),
            r"cosine.*?(\d+\.\d+)",
        ) or "N/A")

    if ok("RUNONBOARD"):
        rp = os.path.join(task_dir, "runonboard/runonboard_report.md")
        for lang in ["Python", "C++"]:
            v = _grep_first(rp, rf"{lang}.*?(\d+\.?\d*)\s*ms")
            if v:
                table.add_row(f"板端 {lang}", f"{v} ms")

    # Pipeline timing from task.md
    task_md = os.path.join(task_dir, "task.md")
    if os.path.isfile(task_md):
        v = _grep_first(task_md, r"端到端.*?(\d+\.?\d*)\s*s")
        if v:
            table.add_row("总耗时", f"{float(v):.0f} s")

    return table


# ─── CLI ───────────────────────────────────────────

def _list_tasks(works_dir: str) -> list[str]:
    """返回 todos/work/ 下按时间倒序的任务目录绝对路径列表。"""
    if not os.path.isdir(works_dir):
        return []
    return sorted(
        [os.path.join(works_dir, d) for d in os.listdir(works_dir)
         if os.path.isdir(os.path.join(works_dir, d))],
        reverse=True,
    )


def _read_key(timeout: float = 0.2) -> str | None:
    """非阻塞读取按键。处理普通键和方向键 escape 序列。

    返回: 'q', 'n', 'p', '1'-'9', 'left', 'right', 或 None
    """
    if select.select([sys.stdin], [], [], timeout)[0]:
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            # Escape 序列：检查是否紧跟着方向键
            if select.select([sys.stdin], [], [], 0.02)[0]:
                seq = sys.stdin.read(2)
                if seq == '[C':
                    return 'right'
                if seq == '[D':
                    return 'left'
            return 'esc'
        return ch
    return None


def _build_footer(task_dir: str, all_tasks: list[str], task_idx: int) -> Panel:
    """构建含任务切换提示的 footer。"""
    total = len(all_tasks)
    name = os.path.basename(task_dir.rstrip("/"))
    source = "task.md" if os.path.isfile(os.path.join(task_dir, "task.md")) else "artifact 推测"
    now = datetime.now().strftime("%H:%M:%S")

    if total > 1:
        hint = f"n/p/←/→:切换任务 1-{min(total,9)}:直达 q:退出"
        parts = [
            f"  {now}  │  任务 [{task_idx+1}/{total}] {name}  ",
            f"│  状态来源: {source}  ",
            f"│  {hint}  ",
        ]
    else:
        parts = [
            f"  {now}  │  任务 {name}  ",
            f"│  状态来源: {source}  ",
            f"│  q 退出  ",
        ]
    return Panel(Text("".join(parts), style="dim"), box=box.ROUNDED)


def main():
    parser = argparse.ArgumentParser(description="Magnetar 工作流 TUI 监控面板")
    parser.add_argument("task_dir", nargs="?", help="TASK_DIR 路径")
    parser.add_argument("--once", action="store_true", help="只输出一次，不持续刷新")
    parser.add_argument("--interval", type=float, default=2.0, help="刷新间隔（秒），默认 2s")
    args = parser.parse_args()

    # 收集所有可用任务目录
    works_dir = os.path.join(os.getcwd(), "todos/work")
    all_tasks = _list_tasks(works_dir)

    if not args.task_dir:
        if all_tasks:
            args.task_dir = all_tasks[0]
            console.print(f"[dim]自动选择最近任务: {args.task_dir}[/dim]")
        else:
            console.print("[red]未找到任务目录。用法: monitor.py <TASK_DIR>[/red]")
            sys.exit(1)

    if not os.path.isdir(args.task_dir):
        console.print(f"[red]目录不存在: {args.task_dir}[/red]")
        sys.exit(1)

    # 确定当前任务在列表中的索引
    task_idx = all_tasks.index(args.task_dir) if args.task_dir in all_tasks else 0
    if args.task_dir not in all_tasks:
        all_tasks.insert(0, args.task_dir)

    if args.once:
        console.print(build_layout(args.task_dir))
        return

    # 切换到 raw 模式以捕获按键
    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    tty.setraw(fd)

    try:
        current = args.task_dir
        layout = build_layout(current)
        # 替换 footer 为含切换提示的版本
        layout["footer"].update(_build_footer(current, all_tasks, task_idx))

        with Live(layout, refresh_per_second=1, screen=True) as live:
            while True:
                key = _read_key(timeout=args.interval)

                if key is not None:
                    if key in ("q", "Q", "esc"):
                        break
                    elif key in ("n", "N", "right"):
                        task_idx = (task_idx + 1) % len(all_tasks)
                        current = all_tasks[task_idx]
                    elif key in ("p", "P", "left"):
                        task_idx = (task_idx - 1) % len(all_tasks)
                        current = all_tasks[task_idx]
                    elif key.isdigit():
                        n = int(key)
                        if 1 <= n <= min(9, len(all_tasks)):
                            task_idx = n - 1
                            current = all_tasks[task_idx]

                layout = build_layout(current)
                layout["footer"].update(_build_footer(current, all_tasks, task_idx))
                live.update(layout)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)

    console.print("\n[dim]监控已停止[/dim]")


if __name__ == "__main__":
    main()
