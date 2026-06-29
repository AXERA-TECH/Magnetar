#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CODEX_SKILLS="${CODEX_HOME:-$HOME/.codex}/skills"

# ── Python 依赖 ─────────────────────────────────────────────────────────────
echo "[1/3] 安装 Python 依赖..."
PY_DEPS=(
    "onnx"
    "onnxruntime"
    "huggingface_hub"
    "optimum[exporters]"
)

if command -v uv &>/dev/null; then
    uv pip install "${PY_DEPS[@]}"
else
    pip install "${PY_DEPS[@]}"
fi

# ── 系统工具检查 ─────────────────────────────────────────────────────────────
echo "[2/3] 检查系统工具..."
check_tool() {
    if command -v "$1" &>/dev/null; then
        echo "  ✓ $1"
    else
        echo "  ✗ $1 未找到 — $2"
    fi
}

check_tool pulsar2          "需手动安装 AXera Pulsar2 工具链"
check_tool cmake            "sudo apt install cmake"
check_tool aarch64-linux-gnu-g++ "sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu"

# ── 注册 Codex Skill ─────────────────────────────────────────────────────────
echo "[3/3] 注册 axmodel-pipeline skill 到 $CODEX_SKILLS ..."
mkdir -p "$CODEX_SKILLS"

SKILL_SRC="$REPO_DIR/.codex/skills/axmodel-pipeline"
SKILL_DST="$CODEX_SKILLS/axmodel-pipeline"

if [ -L "$SKILL_DST" ]; then
    rm "$SKILL_DST"
fi
ln -s "$SKILL_SRC" "$SKILL_DST"
echo "  → $SKILL_DST"

echo ""
echo "安装完成。使用方式："
echo "  /axmodel-pipeline <SOURCE> <TARGET_HARDWARE>"
