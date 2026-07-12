#!/usr/bin/env bash
# Prepare mobile-assistant: copy mobilerun config template and inject API key.
# Does NOT install ADB/Python/mobilerun for you — prints remaining steps.
# Does NOT modify mobilerun 默认用户配置目录（如 Application Support）。
#
# Usage:
#   ./scripts/install-mobile.sh --api-key "ark-xxxx"
#   ./scripts/install-mobile.sh --api-key "$VOLC_ARK_API_KEY" --device-serial R5CTxxxx
#   ./scripts/install-mobile.sh --persist-env   # 可选：追加 export 到 ~/.zshrc 或 ~/.bashrc
set -euo pipefail

API_KEY="${VOLC_ARK_API_KEY:-}"
REPO_ROOT="${OMY_SKILLS_ROOT:-}"
MOBILERUN_HOME_VAL="${MOBILERUN_HOME:-}"
DEVICE_SERIAL=""
PERSIST_ENV=0

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-key) API_KEY="${2:-}"; shift 2 ;;
    --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
    --mobilerun-home) MOBILERUN_HOME_VAL="${2:-}"; shift 2 ;;
    --device-serial) DEVICE_SERIAL="${2:-}"; shift 2 ;;
    --persist-env) PERSIST_ENV=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

resolve_repo_root() {
  local hint="$1"
  if [[ -n "$hint" && -d "$hint/tools/mobilerun" ]]; then
    (cd "$hint" && pwd)
    return
  fi
  local here
  here="$(cd "$(dirname "$0")/.." && pwd)"
  if [[ -d "$here/tools/mobilerun" ]]; then
    echo "$here"
    return
  fi
  echo "Cannot find omy-skills root (expected tools/mobilerun). Set OMY_SKILLS_ROOT." >&2
  exit 1
}

ROOT="$(resolve_repo_root "$REPO_ROOT")"
TEMPLATE="$ROOT/tools/mobilerun/config.template.yaml"
LEGACY="$ROOT/tools/mobilerun/config_multi_windows.yaml"
LOCAL_CONFIG="$ROOT/tools/mobilerun/config.local.yaml"

if [[ -f "$TEMPLATE" ]]; then
  SRC="$TEMPLATE"
elif [[ -f "$LEGACY" ]]; then
  SRC="$LEGACY"
  echo "==> Warning: using deprecated $LEGACY"
else
  echo "Missing template: $TEMPLATE" >&2
  exit 1
fi

echo "==> Repo root: $ROOT"
cp "$SRC" "$LOCAL_CONFIG"

if [[ -n "$API_KEY" ]]; then
  # portable in-place replace
  if command -v perl >/dev/null 2>&1; then
    perl -pi -e "s/YOUR_VOLC_ARK_API_KEY/\Q$API_KEY\E/g" "$LOCAL_CONFIG"
  else
    # fallback: sed (API key must not contain sed metacharacters)
    sed "s/YOUR_VOLC_ARK_API_KEY/${API_KEY//\//\\/}/g" "$LOCAL_CONFIG" > "${LOCAL_CONFIG}.tmp"
    mv "${LOCAL_CONFIG}.tmp" "$LOCAL_CONFIG"
  fi
  echo "==> Injected VOLC API key into local config"
else
  echo "==> Warning: No --api-key / VOLC_ARK_API_KEY. Edit $LOCAL_CONFIG and replace YOUR_VOLC_ARK_API_KEY" >&2
fi

if [[ -n "$DEVICE_SERIAL" ]]; then
  if command -v perl >/dev/null 2>&1; then
    perl -pi -e "s/serial:\\s*emulator-5554/serial: \Q$DEVICE_SERIAL\E/" "$LOCAL_CONFIG"
    perl -pi -e "s/serial:\\s*YOUR_ADB_SERIAL/serial: \Q$DEVICE_SERIAL\E/" "$LOCAL_CONFIG"
    perl -pi -e 's/<<:\s*\*android_emulator/<<: *android_usb/' "$LOCAL_CONFIG"
  else
    sed -i.bak \
      -e "s/serial:[[:space:]]*emulator-5554/serial: $DEVICE_SERIAL/" \
      -e "s/serial:[[:space:]]*YOUR_ADB_SERIAL/serial: $DEVICE_SERIAL/" \
      -e 's/<<:[[:space:]]*\*android_emulator/<<: *android_usb/' \
      "$LOCAL_CONFIG"
    rm -f "${LOCAL_CONFIG}.bak"
  fi
  echo "==> Device serial set to $DEVICE_SERIAL"
else
  echo "==> Tip: pass --device-serial from 'adb devices' for physical phones"
fi

echo "==> Wrote $LOCAL_CONFIG (do not commit if it contains real keys)"
echo ""
echo "Session env (run in current shell):"
echo "  export OMY_SKILLS_ROOT=\"$ROOT\""
echo "  export MOBILERUN_CONFIG=\"$LOCAL_CONFIG\""
if [[ -n "$MOBILERUN_HOME_VAL" ]]; then
  echo "  export MOBILERUN_HOME=\"$MOBILERUN_HOME_VAL\""
fi

if [[ "$PERSIST_ENV" -eq 1 ]]; then
  RC=""
  if [[ -n "${ZSH_VERSION:-}" ]] || [[ "${SHELL:-}" == *zsh* ]]; then
    RC="${HOME}/.zshrc"
  elif [[ -n "${BASH_VERSION:-}" ]] || [[ "${SHELL:-}" == *bash* ]]; then
    RC="${HOME}/.bashrc"
  else
    RC="${HOME}/.profile"
  fi
  {
    echo ""
    echo "# omy-skills mobile-assistant ($(date +%Y-%m-%d))"
    echo "export OMY_SKILLS_ROOT=\"$ROOT\""
    echo "export MOBILERUN_CONFIG=\"$LOCAL_CONFIG\""
    if [[ -n "$MOBILERUN_HOME_VAL" ]]; then
      echo "export MOBILERUN_HOME=\"$MOBILERUN_HOME_VAL\""
    fi
  } >> "$RC"
  echo "==> Appended exports to $RC (re-open shell or source it)"
else
  echo "==> Tip: add --persist-env to append the above exports to your shell rc"
fi

if [[ -n "$MOBILERUN_HOME_VAL" && -d "$MOBILERUN_HOME_VAL" ]]; then
  cp "$LOCAL_CONFIG" "$MOBILERUN_HOME_VAL/config.local.yaml"
  echo "==> Also copied config to $MOBILERUN_HOME_VAL/config.local.yaml"
fi

echo ""
echo "Next steps (if not done yet):"
echo "  1. Python 3.11–3.13 on PATH (or use: uv tool install mobilerun)"
echo "  2. Android Platform Tools; ensure 'adb' works (macOS: brew install --cask android-platform-tools)"
echo "  3. Enable USB debugging; adb devices shows 'device'"
echo "  4. Install engine: uv tool install mobilerun   # or pip/uv from github.com/droidrun/mobilerun"
echo "  5. mobilerun setup && mobilerun ping"
echo "  6. Test: mobilerun run -c \"\$MOBILERUN_CONFIG\" \"打开设置查看Android版本\""
echo ""
echo "Register skills: ./scripts/link-skills.sh"
echo "Then try with Agent: 用手机打开设置"
