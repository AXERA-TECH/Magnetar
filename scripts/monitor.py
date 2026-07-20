#!/usr/bin/env python3
"""Magnetar 工作流 TUI 监控面板。

用法:
    python3 scripts/monitor.py <TASK_DIR>
    python3 scripts/monitor.py todos/work/20260720-mymodel/

从 TASK_DIR 中的 task.md 和阶段产物实时展示 9 阶段流水线进度。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich import box

STAGES = [
    ("ACQUIRE", "获取模型"),
    ("INIT", "初始化工作目录"),
    ("EXPORT", "导出静态ONNX"),
    ("TOOLCHAIN", "准备编译工具链"),
    ("COMPILE", "Pulsar2 编译"),
    ("SIMULATE", "仿真精度对分"),
    ("SDK-GEN", "生成 Python/C++ SDK"),
    ("RUNONBOARD", "板端验证"),
    ("PACKAGE", "打包客户交付包"),
]

STAGE_DIRS = [
    None,       # ACQUIRE - uses cache/acquire/
    None,       # INIT - no artifact dir
    "export",
    None,       # TOOLCHAIN - uses cache/toolchain/
    "compile",
    "simulate",
    "sdk",
    "runonboard",
    "package",
]

STAGE_FILES = {
    "ACQUIRE": "cache/acquire/manifest.json",
    "EXPORT": "export/model.onnx",
    "COMPILE": "compile/model.axmodel",
    "SIMULATE": "simulate/simulate_report.md",
    "SDK-GEN": "sdk/sdk_report.md",
    "RUNONBOARD": "runonboard/runonboard_report.md",
    "PACKAGE": "package/README.md",
}

console = Console()

def parse_task_md(path: str) -> dict:
    """Parse task.md to extract stage statuses."""
    result: dict = {}
    if not os.path.exists(path):
        return result
    
    with open(path) as f:
        content = f.read()
    
    # Try to find stage status table
    for stage_name, _ in STAGES:
        # Look for stage status markers
        patterns = [
            rf"{stage_name}.*?✓",
            rf"{stage_name}.*?完成",
            rf"{stage_name}.*?通过",
            rf"{stage_name}.*?COMPLETED",
            rf"{stage_name}.*?PASS",
        ]
        for pat in patterns:
            if re.search(pat, content, re.IGNORECASE):
                result[stage_name] = "completed"
                break
        else:
            # Check if stage has started
            if re.search(rf"{stage_name}", content, re.IGNORECASE):
                result[stage_name] = "running"
    
    return result

def check_artifact(task_dir: str, stage_name: str) -> str:
    """Check if a stage's key artifact exists."""
    if stage_name in STAGE_FILES:
        artifact = os.path.join(task_dir, STAGE_FILES[stage_name])
        if os.path.exists(artifact):
            size = os.path.getsize(artifact)
            if size > 0:
                return "completed"
            return "running"
    
    # Check stage directory for any content
    for i, (sn, _) in enumerate(STAGES):
        if sn == stage_name and STAGE_DIRS[i]:
            sdir = os.path.join(task_dir, STAGE_DIRS[i])
            if os.path.isdir(sdir) and os.listdir(sdir):
                return "completed"
    
    return "pending"

def get_stage_statuses(task_dir: str) -> list[tuple[str, str, str]]:
    """Return [(stage_name, status, detail), ...] for all 9 stages."""
    task_md_path = os.path.join(task_dir, "task.md")
    md_statuses = parse_task_md(task_md_path)
    
    # Determine RUNONBOARD skip
    analysis_path = os.path.join(task_dir, "analysis.md")
    board_skip = False
    if os.path.exists(analysis_path):
        with open(analysis_path) as f:
            if "N/A" in f.read() and "BOARD" in f.read():
                board_skip = True
    
    results = []
    for stage_name, stage_desc in STAGES:
        # Priority: artifact > task.md > default
        artifact_status = check_artifact(task_dir, stage_name)
        md_status = md_statuses.get(stage_name, "pending")
        
        if artifact_status == "completed":
            status = "completed"
        elif md_status == "running":
            status = "running"
        elif artifact_status == "running":
            status = "running"
        else:
            status = "pending"
        
        # Special case for RUNONBOARD
        if stage_name == "RUNONBOARD" and board_skip:
            status = "skipped"
        
        # Build detail string
        detail = _get_stage_detail(task_dir, stage_name, status)
        
        results.append((stage_name, stage_desc, status, detail))
    
    return results

def _get_stage_detail(task_dir: str, stage_name: str, status: str) -> str:
    """Get human-readable detail for a stage."""
    if status == "pending":
        return ""
    if status == "skipped":
        return "N/A — 未提供 BOARD"
    
    if stage_name == "ACQUIRE":
        manifest = os.path.join(task_dir, "cache/acquire/manifest.json")
        if os.path.exists(manifest):
            try:
                with open(manifest) as f:
                    data = json.load(f)
                    src = data.get("source", "")
                    if len(src) > 40:
                        src = src[:37] + "..."
                    return f"来源: {src or '已获取'}"
            except Exception:
                pass
        return "已获取模型文件"
    
    if stage_name == "EXPORT":
        onnx = os.path.join(task_dir, "export/model.onnx")
        if os.path.exists(onnx):
            size_mb = os.path.getsize(onnx) / 1024 / 1024
            return f"ONNX: {size_mb:.1f} MB"
        return ""
    
    if stage_name == "COMPILE":
        axmodel = os.path.join(task_dir, "compile/model.axmodel")
        if os.path.exists(axmodel):
            size_kb = os.path.getsize(axmodel) / 1024
            return f"AXMODEL: {size_kb:.0f} KB"
        return ""
    
    if stage_name == "SIMULATE":
        report = os.path.join(task_dir, "simulate/simulate_report.md")
        if os.path.exists(report):
            with open(report) as f:
                content = f.read()
                m = re.search(r"cosine.*?(\d+\.\d+)", content)
                if m:
                    return f"cosine: {m.group(1)}"
        return ""
    
    if stage_name == "SDK-GEN":
        return "Python/C++ SDK 已生成"
    
    if stage_name == "RUNONBOARD":
        report = os.path.join(task_dir, "runonboard/runonboard_report.md")
        if os.path.exists(report):
            with open(report) as f:
                content = f.read()
                m = re.search(r"Python.*?(\d+\.?\d*)\s*ms", content)
                if m:
                    return f"延迟: {m.group(1)} ms"
        return "板端验证完成"
    
    if stage_name == "PACKAGE":
        pkg = os.path.join(task_dir, "package/README.md")
        if os.path.exists(pkg):
            # Count package files
            count = 0
            for root, _, files in os.walk(os.path.join(task_dir, "package")):
                count += len(files)
            return f"交付包: {count} 个文件"
        return ""
    
    return ""

def build_layout(task_dir: str) -> Layout:
    """Build the rich layout for the dashboard."""
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    
    # Header
    task_name = os.path.basename(task_dir.rstrip("/"))
    header_text = Text(f"  Magnetar Pipeline — {task_name}", style="bold cyan")
    layout["header"].update(Panel(header_text, box=box.ROUNDED))
    
    # Body: pipeline stages + metrics
    layout["body"].split_row(
        Layout(name="stages", ratio=2),
        Layout(name="metrics", ratio=1),
    )
    
    # Stages
    stages_table = _build_stages_table(task_dir)
    layout["stages"].update(Panel(stages_table, title="流水线阶段", border_style="blue"))
    
    # Metrics
    metrics_panel = _build_metrics_panel(task_dir)
    layout["metrics"].update(Panel(metrics_panel, title="关键指标", border_style="green"))
    
    # Footer
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer_text = Text(f"  刷新: {now}  |  按 Ctrl+C 退出  |  TASK_DIR: {task_dir}", style="dim")
    layout["footer"].update(Panel(footer_text, box=box.ROUNDED))
    
    return layout

def _build_stages_table(task_dir: str) -> Table:
    """Build the pipeline stages table."""
    statuses = get_stage_statuses(task_dir)
    
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("#", width=2, style="dim")
    table.add_column("阶段", width=12)
    table.add_column("状态", width=10)
    table.add_column("详情", width=28)
    
    status_icons = {
        "completed": ("✓", "green"),
        "running": ("●", "yellow"),
        "pending": ("○", "dim"),
        "skipped": ("−", "dim"),
    }
    
    for i, (name, desc, status, detail) in enumerate(statuses, 1):
        icon, color = status_icons.get(status, ("?", "dim"))
        status_text = {
            "completed": "完成",
            "running": "进行中",
            "pending": "等待",
            "skipped": "跳过",
        }.get(status, status)
        
        table.add_row(
            str(i),
            name,
            f"[{color}]{icon} {status_text}[/{color}]",
            f"[{color}]{detail}[/{color}]" if detail else "",
        )
    
    return table

def _build_metrics_panel(task_dir: str) -> Table:
    """Build key metrics summary."""
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    table.add_column("指标", style="dim")
    table.add_column("值", style="bold")
    
    # Model name
    task_name = os.path.basename(task_dir.rstrip("/"))
    table.add_row("任务", task_name)
    
    # ONNX size
    onnx_path = os.path.join(task_dir, "export/model.onnx")
    if os.path.exists(onnx_path):
        table.add_row("ONNX", f"{os.path.getsize(onnx_path)/1024/1024:.1f} MB")
    
    # AXMODEL size
    axmodel_path = os.path.join(task_dir, "compile/model.axmodel")
    if os.path.exists(axmodel_path):
        table.add_row("AXMODEL", f"{os.path.getsize(axmodel_path)/1024:.0f} KB")
    
    # Compression ratio
    if os.path.exists(onnx_path) and os.path.exists(axmodel_path):
        ratio = os.path.getsize(onnx_path) / max(os.path.getsize(axmodel_path), 1)
        table.add_row("压缩比", f"{ratio:.1f}:1")
    
    # Accuracy
    sim_path = os.path.join(task_dir, "simulate/simulate_report.md")
    if os.path.exists(sim_path):
        with open(sim_path) as f:
            content = f.read()
            m = re.search(r"cosine.*?(\d+\.\d+)\s*±\s*(\d+\.\d+)", content)
            if m:
                table.add_row("cosine", f"{m.group(1)} ± {m.group(2)}")
            else:
                m = re.search(r"cosine.*?(\d+\.\d+)", content)
                if m:
                    table.add_row("cosine", m.group(1))
    
    # MACs
    compile_report = os.path.join(task_dir, "compile/compile_report.md")
    if os.path.exists(compile_report):
        with open(compile_report) as f:
            content = f.read()
            m = re.search(r"MACs.*?(\d+\.?\d*)\s*G", content)
            if m:
                table.add_row("MACs", f"{m.group(1)} G")
    
    # Board latency
    board_report = os.path.join(task_dir, "runonboard/runonboard_report.md")
    if os.path.exists(board_report):
        with open(board_report) as f:
            content = f.read()
            for lang in ["Python", "C++"]:
                m = re.search(rf"{lang}.*?(\d+\.?\d*)\s*ms", content)
                if m:
                    table.add_row(f"板端{lang}", f"{m.group(1)} ms")
    
    # Pipeline timing
    task_md = os.path.join(task_dir, "task.md")
    if os.path.exists(task_md):
        with open(task_md) as f:
            content = f.read()
            m = re.search(r"总计.*?(\d+\.?\d*)\s*s", content)
            if m:
                table.add_row("总耗时", f"{float(m.group(1)):.0f} s")
    
    return table

def make_layout(task_dir: str) -> Layout:
    """Layout factory for Live display."""
    return build_layout(task_dir)

def main():
    parser = argparse.ArgumentParser(description="Magnetar 工作流 TUI 监控面板")
    parser.add_argument("task_dir", nargs="?", help="TASK_DIR 路径")
    parser.add_argument("--once", action="store_true", help="只输出一次，不持续刷新")
    parser.add_argument("--interval", type=float, default=2.0, help="刷新间隔（秒），默认 2s")
    args = parser.parse_args()
    
    if not args.task_dir:
        # Try to find the most recent task
        works_dir = os.path.join(os.getcwd(), "todos/work")
        if os.path.isdir(works_dir):
            dirs = sorted(
                [d for d in os.listdir(works_dir) if os.path.isdir(os.path.join(works_dir, d))],
                reverse=True,
            )
            if dirs:
                args.task_dir = os.path.join(works_dir, dirs[0])
                console.print(f"[dim]自动选择最近任务: {args.task_dir}[/dim]")
            else:
                console.print("[red]未找到任务目录。用法: monitor.py <TASK_DIR>[/red]")
                sys.exit(1)
        else:
            console.print("[red]未找到 todos/work/ 目录。请指定 TASK_DIR[/red]")
            sys.exit(1)
    
    if not os.path.isdir(args.task_dir):
        console.print(f"[red]目录不存在: {args.task_dir}[/red]")
        sys.exit(1)
    
    if args.once:
        console.print(build_layout(args.task_dir))
        return
    
    try:
        with Live(build_layout(args.task_dir), refresh_per_second=1, screen=True) as live:
            while True:
                time.sleep(args.interval)
                live.update(build_layout(args.task_dir))
    except KeyboardInterrupt:
        console.print("\n[dim]监控已停止[/dim]")

if __name__ == "__main__":
    main()
