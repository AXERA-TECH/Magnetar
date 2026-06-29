#!/usr/bin/env bash
set -euo pipefail

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
echo "Try it with:"
echo '  Use $magnetar to convert SOURCE to an AXMODEL package with Python and C++ SDKs.'
