#!/usr/bin/env bash
# 将 omy-skills 下的 skills/* 软链到常见 Agent 技能目录（仅改技能发现路径，不改运行时密钥配置）。
#
# Usage:
#   ./scripts/link-skills.sh              # 链接到已存在的目标目录
#   ./scripts/link-skills.sh --dry-run
#   ./scripts/link-skills.sh --unlink
set -euo pipefail

DRY_RUN=0
UNLINK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --unlink) UNLINK=1; shift ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_SRC="$ROOT/skills"
if [[ ! -d "$SKILLS_SRC" ]]; then
  echo "Missing $SKILLS_SRC" >&2
  exit 1
fi

# 仅链接到「已存在」的父目录，避免擅自创建用户未使用的产品目录
CANDIDATES=(
  "$HOME/.claude/skills"
  "$HOME/.codex/skills"
  "$HOME/.agents/skills"
  "$HOME/.opencode/skills"
  "$HOME/.opencode/.opencode/skill"
)

link_one() {
  local name="$1"
  local src="$SKILLS_SRC/$name"
  local dest_parent="$2"
  local dest="$dest_parent/$name"

  if [[ ! -d "$src" || ! -f "$src/SKILL.md" ]]; then
    echo "skip (no SKILL.md): $src"
    return
  fi
  if [[ ! -d "$dest_parent" ]]; then
    return
  fi

  if [[ "$UNLINK" -eq 1 ]]; then
    if [[ -L "$dest" ]]; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "DRY unlink $dest"
      else
        rm -f "$dest"
        echo "unlinked $dest"
      fi
    fi
    return
  fi

  if [[ -e "$dest" && ! -L "$dest" ]]; then
    echo "skip (exists, not symlink): $dest"
    return
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY link $dest -> $src"
  else
    ln -sfn "$src" "$dest"
    echo "linked $dest -> $src"
  fi
}

shopt -s nullglob
for skill_dir in "$SKILLS_SRC"/*/; do
  name="$(basename "$skill_dir")"
  for parent in "${CANDIDATES[@]}"; do
    link_one "$name" "$parent"
  done
done

echo ""
echo "Done. OMY_SKILLS_ROOT tip: export OMY_SKILLS_ROOT=\"$ROOT\""
echo "Only existing skill roots were used; create a target dir first if needed, e.g. mkdir -p ~/.claude/skills"
