#!/usr/bin/env python3
"""Magnetar 工作流 HTML 报告生成器。

用法:
    python3 scripts/generate_report.py <TASK_DIR> [-o output.html]

从 TASK_DIR 中的阶段产物生成自包含 HTML 仪表盘。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

STAGES = [
    ("ACQUIRE", "获取模型", "cache/acquire/manifest.json"),
    ("INIT", "初始化工作目录", "task.md"),
    ("EXPORT", "导出静态ONNX", "export/model.onnx"),
    ("TOOLCHAIN", "准备编译工具链", None),
    ("COMPILE", "Pulsar2 编译", "compile/model.axmodel"),
    ("SIMULATE", "仿真精度对分", "simulate/simulate_report.md"),
    ("SDK-GEN", "生成 SDK", "sdk/sdk_report.md"),
    ("RUNONBOARD", "板端验证", "runonboard/runonboard_report.md"),
    ("PACKAGE", "打包交付", "package/README.md"),
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Magnetar Pipeline Report — {task_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0d1117; color: #c9d1d9; line-height: 1.6; padding: 24px;
}}
h1 {{ color: #58a6ff; font-size: 24px; margin-bottom: 4px; }}
h2 {{ color: #f0883e; font-size: 18px; margin: 24px 0 12px; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
.subtitle {{ color: #8b949e; font-size: 14px; margin-bottom: 24px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.card {{
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    padding: 16px; text-align: center;
}}
.card .value {{ font-size: 28px; font-weight: bold; color: #58a6ff; }}
.card .label {{ font-size: 13px; color: #8b949e; margin-top: 4px; }}
.pipeline {{ display: flex; align-items: center; gap: 0; margin-bottom: 24px; overflow-x: auto; padding: 8px 0; }}
.stage {{
    display: flex; flex-direction: column; align-items: center; min-width: 100px;
    padding: 12px 8px; border-radius: 8px; text-align: center; font-size: 12px;
}}
.stage .icon {{ font-size: 24px; margin-bottom: 4px; }}
.stage .name {{ font-weight: bold; }}
.stage .desc {{ color: #8b949e; font-size: 11px; }}
.arrow {{ color: #30363d; font-size: 20px; margin: 0 2px; flex-shrink: 0; }}
.done {{ background: #0d3320; border: 1px solid #1a7f46; }}
.done .icon {{ color: #3fb950; }}
.done .name {{ color: #3fb950; }}
.running {{ background: #1a2b3c; border: 1px solid #1f6feb; }}
.running .icon {{ color: #58a6ff; }}
.running .name {{ color: #58a6ff; }}
.pending {{ background: #161b22; border: 1px solid #30363d; }}
.pending .icon {{ color: #484f58; }}
.pending .name {{ color: #484f58; }}
.skipped {{ background: #161b22; border: 1px dashed #30363d; }}
.skipped .icon, .skipped .name {{ color: #484f58; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; font-size: 14px; }}
th {{ color: #8b949e; font-weight: 600; }}
.mono {{ font-family: "SF Mono", "Fira Code", monospace; font-size: 13px; }}
.na {{ color: #484f58; font-style: italic; }}
footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #30363d; color: #484f58; font-size: 12px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
.badge-pass {{ background: #0d3320; color: #3fb950; }}
.badge-warn {{ background: #2e2a10; color: #d29922; }}
.badge-fail {{ background: #3d1015; color: #f85149; }}
</style>
</head>
<body>
<h1>🔄 Magnetar Pipeline Report</h1>
<p class="subtitle">{task_name} &nbsp;|&nbsp; 生成时间: {generated_at}</p>

<h2>流水线</h2>
<div class="pipeline">
{pipeline_html}
</div>

<h2>关键指标</h2>
<div class="grid">
{metrics_html}
</div>

<h2>阶段详情</h2>
{details_html}

<footer>
Magnetar &mdash; AXera AI Model Deployment Pipeline &nbsp;|&nbsp; {generated_at}
</footer>
</body>
</html>"""

def check_status(task_dir: str, stage_name: str, artifact: str | None) -> str:
    """Determine stage status."""
    if artifact and os.path.exists(os.path.join(task_dir, artifact)):
        if os.path.getsize(os.path.join(task_dir, artifact)) > 0:
            return "done"
        return "running"
    
    # Check stage dir
    stage_dir_map = {
        "INIT": None, "TOOLCHAIN": None,
        "EXPORT": "export", "COMPILE": "compile",
        "SIMULATE": "simulate", "SDK-GEN": "sdk",
        "RUNONBOARD": "runonboard", "PACKAGE": "package",
    }
    
    sdir = stage_dir_map.get(stage_name)
    if sdir:
        full = os.path.join(task_dir, sdir)
        if os.path.isdir(full) and os.listdir(full):
            return "done"
    
    # Check task.md for running status
    task_md = os.path.join(task_dir, "task.md")
    if os.path.exists(task_md):
        with open(task_md) as f:
            if re.search(rf"{stage_name}.*?(进行中|running)", f.read(), re.IGNORECASE):
                return "running"
    
    return "pending"

def build_pipeline_html(task_dir: str) -> str:
    """Build pipeline row HTML."""
    parts = []
    for i, (name, desc, artifact) in enumerate(STAGES):
        # Check skip for RUNONBOARD
        if name == "RUNONBOARD":
            analysis = os.path.join(task_dir, "analysis.md")
            if os.path.exists(analysis):
                with open(analysis) as f:
                    if "N/A" in f.read() and "BOARD" in f.read():
                        status = "skipped"
                    else:
                        status = check_status(task_dir, name, artifact)
            else:
                status = check_status(task_dir, name, artifact)
        else:
            status = check_status(task_dir, name, artifact)
        
        icons = {"done": "✓", "running": "◉", "pending": "○", "skipped": "−"}
        
        parts.append(
            f'<div class="stage {status}">'
            f'<span class="icon">{icons.get(status, "?")}</span>'
            f'<span class="name">{name}</span>'
            f'<span class="desc">{desc}</span>'
            f'</div>'
        )
        
        if i < len(STAGES) - 1:
            parts.append('<span class="arrow">→</span>')
    
    return "\n".join(parts)

def build_metrics_html(task_dir: str) -> str:
    """Build metrics cards HTML."""
    cards = []
    
    # ONNX size
    onnx = os.path.join(task_dir, "export/model.onnx")
    if os.path.exists(onnx):
        cards.append(_card(f"{os.path.getsize(onnx)/1024/1024:.1f} MB", "ONNX 模型"))
    
    # AXMODEL size
    axm = os.path.join(task_dir, "compile/model.axmodel")
    if os.path.exists(axm):
        cards.append(_card(f"{os.path.getsize(axm)/1024:.0f} KB", "AXMODEL"))
    
    # Compression ratio
    if os.path.exists(onnx) and os.path.exists(axm):
        r = os.path.getsize(onnx) / max(os.path.getsize(axm), 1)
        cards.append(_card(f"{r:.1f}:1", "压缩比"))
    
    # Cosine
    sim = os.path.join(task_dir, "simulate/simulate_report.md")
    if os.path.exists(sim):
        with open(sim) as f:
            c = f.read()
            m = re.search(r"cosine.*?(\d+\.\d+)\s*±\s*(\d+\.\d+)", c)
            if m:
                cards.append(_card(f"{m.group(1)}", f"cosine ±{m.group(2)}"))
            else:
                m = re.search(r"cosine.*?(\d+\.\d+)", c)
                if m:
                    cards.append(_card(m.group(1), "cosine"))
    
    # MACs
    cr = os.path.join(task_dir, "compile/compile_report.md")
    if os.path.exists(cr):
        with open(cr) as f:
            c = f.read()
            m = re.search(r"MACs.*?(\d+\.?\d*)\s*G", c)
            if m:
                cards.append(_card(f"{m.group(1)} G", "MACs"))
    
    # Board latency
    br = os.path.join(task_dir, "runonboard/runonboard_report.md")
    if os.path.exists(br):
        with open(br) as f:
            c = f.read()
            for lang in ["Python", "C++"]:
                m = re.search(rf"{lang}.*?(\d+\.?\d*)\s*ms", c)
                if m:
                    cards.append(_card(f"{m.group(1)} ms", f"板端 {lang}"))
    
    # Total time
    tm = os.path.join(task_dir, "task.md")
    if os.path.exists(tm):
        with open(tm) as f:
            c = f.read()
            m = re.search(r"总计.*?(\d+\.?\d*)\s*s", c)
            if m:
                cards.append(_card(f"{float(m.group(1)):.0f} s", "总耗时"))
    
    if not cards:
        cards.append(_card("—", "等待数据"))
    
    return "\n".join(cards)

def _card(value: str, label: str) -> str:
    return f'<div class="card"><div class="value">{value}</div><div class="label">{label}</div></div>'

def build_details_html(task_dir: str) -> str:
    """Build stage details table."""
    rows = []
    
    for name, desc, artifact in STAGES:
        status = check_status(task_dir, name, artifact)
        
        status_badges = {
            "done": '<span class="badge badge-pass">完成</span>',
            "running": '<span class="badge badge-warn">进行中</span>',
            "pending": '<span class="badge badge-fail">等待</span>',
            "skipped": '<span class="badge" style="background:#161b22;color:#484f58;">跳过</span>',
        }
        
        detail = _get_detail(task_dir, name, status)
        
        rows.append(
            f'<tr><td>{name}</td><td>{desc}</td>'
            f'<td>{status_badges.get(status, "?")}</td>'
            f'<td class="mono">{detail}</td></tr>'
        )
    
    table = (
        '<table><thead><tr>'
        '<th>阶段</th><th>说明</th><th>状态</th><th>详情</th>'
        '</tr></thead><tbody>'
        + "\n".join(rows) +
        '</tbody></table>'
    )
    return table

def _get_detail(task_dir: str, name: str, status: str) -> str:
    if status == "pending":
        return '<span class="na">—</span>'
    if status == "skipped":
        return '<span class="na">N/A — 未提供 BOARD</span>'
    
    details = {
        "EXPORT": _file_size(os.path.join(task_dir, "export/model.onnx"), "MB"),
        "COMPILE": _file_size(os.path.join(task_dir, "compile/model.axmodel"), "KB"),
        "SIMULATE": _sim_detail(task_dir),
        "RUNONBOARD": _board_detail(task_dir),
        "PACKAGE": _pkg_detail(task_dir),
    }
    
    if name in details and details[name]:
        return details[name]
    
    return "✓"

def _file_size(path: str, unit: str) -> str:
    if os.path.exists(path):
        size = os.path.getsize(path)
        if unit == "MB":
            return f"{size/1024/1024:.1f} MB"
        return f"{size/1024:.0f} KB"
    return ""

def _sim_detail(task_dir: str) -> str:
    path = os.path.join(task_dir, "simulate/simulate_report.md")
    if os.path.exists(path):
        with open(path) as f:
            c = f.read()
            parts = []
            m = re.search(r"cosine.*?(\d+\.\d+)\s*±\s*(\d+\.\d+)", c)
            if m:
                parts.append(f"cosine: {m.group(1)}±{m.group(2)}")
            m = re.search(r"MAE.*?(\d+\.\d+)\s*±\s*(\d+\.\d+)", c)
            if m:
                parts.append(f"MAE: {m.group(1)}±{m.group(2)}")
            return " / ".join(parts) if parts else "✓"
    return ""

def _board_detail(task_dir: str) -> str:
    path = os.path.join(task_dir, "runonboard/runonboard_report.md")
    if os.path.exists(path):
        with open(path) as f:
            c = f.read()
            m = re.search(r"Python.*?(\d+\.?\d*)\s*ms", c)
            if m:
                return f"延迟: {m.group(1)} ms"
    return ""

def _pkg_detail(task_dir: str) -> str:
    pkg = os.path.join(task_dir, "package")
    if os.path.isdir(pkg):
        count = sum(len(files) for _, _, files in os.walk(pkg))
        return f"{count} 个文件"
    return ""

def generate(task_dir: str, output: str):
    task_name = os.path.basename(task_dir.rstrip("/"))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    pipeline_html = build_pipeline_html(task_dir)
    metrics_html = build_metrics_html(task_dir)
    details_html = build_details_html(task_dir)
    
    html = HTML_TEMPLATE.format(
        task_name=task_name,
        generated_at=generated_at,
        pipeline_html=pipeline_html,
        metrics_html=metrics_html,
        details_html=details_html,
    )
    
    with open(output, "w") as f:
        f.write(html)
    
    print(f"HTML 报告已生成: {output}")
    print(f"  文件大小: {os.path.getsize(output)/1024:.1f} KB")
    print(f"  可直接用浏览器打开: file://{os.path.abspath(output)}")

def main():
    parser = argparse.ArgumentParser(description="Magnetar HTML 报告生成器")
    parser.add_argument("task_dir", nargs="?", help="TASK_DIR 路径")
    parser.add_argument("-o", "--output", help="输出文件路径")
    args = parser.parse_args()
    
    if not args.task_dir:
        works_dir = os.path.join(os.getcwd(), "todos/work")
        if os.path.isdir(works_dir):
            dirs = sorted(
                [d for d in os.listdir(works_dir) if os.path.isdir(os.path.join(works_dir, d))],
                reverse=True,
            )
            if dirs:
                args.task_dir = os.path.join(works_dir, dirs[0])
            else:
                print("未找到任务目录", file=sys.stderr)
                sys.exit(1)
        else:
            print("未找到 todos/work/ 目录", file=sys.stderr)
            sys.exit(1)
    
    if not os.path.isdir(args.task_dir):
        print(f"目录不存在: {args.task_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not args.output:
        args.output = os.path.join(args.task_dir, "dashboard.html")
    
    generate(args.task_dir, args.output)

if __name__ == "__main__":
    main()
