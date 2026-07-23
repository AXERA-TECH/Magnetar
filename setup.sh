#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

check_dep() {
    local name="$1"
    local hint="${2:-}"
    if command -v "$name" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $name"
        return 0
    else
        echo -e "  ${RED}✗${NC} $name — 未找到${hint:+ 安装: $hint}"
        return 1
    fi
}

check_docker() {
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} docker ($(docker --version | cut -d' ' -f3 | tr -d ','))"
        return 0
    elif command -v docker &>/dev/null; then
        echo -e "  ${YELLOW}⚠${NC} docker 已安装但未运行 — sudo systemctl start docker"
        return 1
    else
        echo -e "  ${RED}✗${NC} docker — 未找到 安装: curl -fsSL https://get.docker.com | sh"
        return 1
    fi
}

usage() {
    cat <<'EOF'
Usage: ./setup.sh [--copy|--link] [--force]

Install the Magnetar Codex skill into:
  ${CODEX_HOME:-$HOME/.codex}/skills/magnetar

Options:
  --copy   Copy the skill directory. This is the default.
  --link   Install as a symlink to this repository.
  --force  Replace an existing installed skill.
  -h, --help
           Show this help.
EOF
}

echo ""
echo -e "${CYAN}=== Magnetar 环境依赖检查 ===${NC}"
echo ""
DEPS_OK=0
check_dep git || DEPS_OK=1
if command -v python3 &>/dev/null; then
    py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    py_major=$(echo "$py_ver" | cut -d. -f1)
    py_minor=$(echo "$py_ver" | cut -d. -f2)
    if [ "$py_major" -eq 3 ] && [ "$py_minor" -ge 10 ] && [ "$py_minor" -le 13 ]; then
        echo -e "  ${GREEN}✓${NC} python3 $py_ver"
    else
        echo -e "  ${RED}✗${NC} python3 $py_ver — 需要 3.10-3.13（3.14 无 onnxruntime wheels）"
        DEPS_OK=1
    fi
else
    echo -e "  ${RED}✗${NC} python3 — 未找到 安装: apt install python3"
    DEPS_OK=1
fi
check_dep uv "curl -LsSf https://astral.sh/uv/install.sh | sh" || DEPS_OK=1
check_docker || DEPS_OK=1
check_dep cmake "apt install cmake" || DEPS_OK=1
check_dep bash || DEPS_OK=1
echo ""

if [ "$DEPS_OK" -ne 0 ]; then
    echo -e "${YELLOW}部分依赖缺失，请先安装后再运行 setup.sh。${NC}"
    echo ""
fi

mode="copy"
force="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy)
      mode="copy"
      ;;
    --link)
      mode="link"
      ;;
    --force)
      force="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_src="$repo_root/.codex/skills/magnetar"
codex_home="${CODEX_HOME:-$HOME/.codex}"
skills_dir="$codex_home/skills"
skill_dst="$skills_dir/magnetar"

if [[ ! -f "$skill_src/SKILL.md" ]]; then
  echo "Missing skill source: $skill_src" >&2
  exit 1
fi

mkdir -p "$skills_dir"

if [[ -e "$skill_dst" || -L "$skill_dst" ]]; then
  if [[ "$force" != "true" ]]; then
    echo "Skill already exists: $skill_dst" >&2
    echo "Re-run with --force to replace it." >&2
    exit 1
  fi
  rm -rf "$skill_dst"
fi

case "$mode" in
  copy)
    cp -R "$skill_src" "$skill_dst"
    ;;
  link)
    ln -s "$skill_src" "$skill_dst"
    ;;
esac

echo "Installed Magnetar skill:"
echo "  source: $skill_src"
echo "  target: $skill_dst"
echo
echo "接下来请安装 Pulsar2 编译环境:"
echo "  ./scripts/install_pulsar2.sh"
echo
echo "Try it with:"
echo '  Use $magnetar to convert SOURCE to an AXMODEL package with Python and C++ SDKs.'

if [ "$DEPS_OK" -ne 0 ]; then
    echo ""
    echo -e "${YELLOW}注意: 部分依赖缺失，Pulsar2 编译和 C++ SDK 构建可能失败。${NC}"
fi
