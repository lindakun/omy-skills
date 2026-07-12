#!/usr/bin/env bash
# Prepare mac-assistant / macrun on macOS.
# Only writes repo-local config; does not change system privacy settings.
#
# Usage:
#   ./scripts/install-mac.sh --api-key "ark-xxxx"
#   ./scripts/install-mac.sh --api-key "$VOLC_ARK_API_KEY" --persist-env
set -euo pipefail

API_KEY="${VOLC_ARK_API_KEY:-}"
REPO_ROOT="${OMY_SKILLS_ROOT:-}"
PYTHON_BIN="${MACRUN_PYTHON:-}"
PERSIST_ENV=0

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-key) API_KEY="${2:-}"; shift 2 ;;
    --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
    --python) PYTHON_BIN="${2:-}"; shift 2 ;;
    --persist-env) PERSIST_ENV=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "install-mac.sh only supports macOS (Darwin)." >&2
  exit 1
fi

resolve_repo_root() {
  local hint="$1"
  if [[ -n "$hint" && -d "$hint/tools/macrun" ]]; then
    (cd "$hint" && pwd)
    return
  fi
  local here
  here="$(cd "$(dirname "$0")/.." && pwd)"
  if [[ -d "$here/tools/macrun" ]]; then
    echo "$here"
    return
  fi
  echo "Cannot find omy-skills root (expected tools/macrun). Set OMY_SKILLS_ROOT." >&2
  exit 1
}

pick_python() {
  if [[ -n "$PYTHON_BIN" ]]; then
    echo "$PYTHON_BIN"
    return
  fi
  local c
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      local ver
      ver="$("$c" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      # prefer 3.11+
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'; then
        echo "$c"
        return
      fi
    fi
  done
  echo "Need Python 3.11+. Install via brew/uv/miniconda." >&2
  exit 1
}

ROOT="$(resolve_repo_root "$REPO_ROOT")"
MACRUN="$ROOT/tools/macrun"
TEMPLATE="$MACRUN/config.template.yaml"
LOCAL_CFG="$MACRUN/config.local.yaml"
PY="$(pick_python)"

echo "==> Repo root: $ROOT"
echo "==> Python:    $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Missing $TEMPLATE" >&2
  exit 1
fi

# venv
VENV="$MACRUN/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "==> Creating venv..."
  "$PY" -m venv "$VENV"
else
  echo "==> venv exists"
fi

echo "==> Installing macrun..."
"$VENV/bin/pip" install -U pip
"$VENV/bin/pip" install -e "$MACRUN"

# config
cp "$TEMPLATE" "$LOCAL_CFG"
if [[ -n "$API_KEY" ]]; then
  if command -v perl >/dev/null 2>&1; then
    perl -pi -e "s/YOUR_VOLC_ARK_API_KEY/\Q$API_KEY\E/g" "$LOCAL_CFG"
  else
    sed "s/YOUR_VOLC_ARK_API_KEY/${API_KEY//\//\\/}/g" "$LOCAL_CFG" > "${LOCAL_CFG}.tmp"
    mv "${LOCAL_CFG}.tmp" "$LOCAL_CFG"
  fi
  echo "==> Injected API key into config.local.yaml"
else
  echo "==> Warning: no --api-key / VOLC_ARK_API_KEY; edit $LOCAL_CFG" >&2
fi
echo "==> Wrote $LOCAL_CFG (do not commit if it has real keys)"

echo ""
echo "Session env:"
echo "  export OMY_SKILLS_ROOT=\"$ROOT\""
echo "  export MACRUN_CONFIG=\"$LOCAL_CFG\""
echo "  export PATH=\"$VENV/bin:\$PATH\""

if [[ "$PERSIST_ENV" -eq 1 ]]; then
  RC="${HOME}/.zshrc"
  if [[ "${SHELL:-}" == *bash* ]]; then RC="${HOME}/.bashrc"; fi
  {
    echo ""
    echo "# omy-skills mac-assistant ($(date +%Y-%m-%d))"
    echo "export OMY_SKILLS_ROOT=\"$ROOT\""
    echo "export MACRUN_CONFIG=\"$LOCAL_CFG\""
    echo "export PATH=\"$VENV/bin:\$PATH\""
  } >> "$RC"
  echo "==> Appended exports to $RC"
else
  echo "==> Tip: add --persist-env to append exports to shell rc"
fi

echo ""
echo "Next:"
echo "  1. 系统设置 → 隐私与安全性 → 辅助功能 + 屏幕录制 → 授权你的终端/Agent 宿主"
echo "  2. source venv:  source \"$VENV/bin/activate\""
echo "  3. macrun doctor"
echo "  4. macrun run \"打开 TextEdit，输入 Hello mac-assistant\""
echo "  5. ./scripts/link-skills.sh   # 注册到 Agent"
echo ""
echo "WeChat tip: goal 中强制剪贴板粘贴中文；见 skills/mac-assistant/SKILL.md"
