#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./launchd/install_launchd.sh --worldosint-root /abs/path/worldosint-headless --mirofish-root /abs/path/MiroFish [options]

Options:
  --worldosint-root PATH         Absolute path to the WorldOSINT repo
  --mirofish-root PATH           Absolute path to the MiroFish repo
  --worldosint-base-url URL      Base URL for the WorldOSINT app (default: http://127.0.0.1:3000)
  --worldosint-ws-port PORT      WebSocket bridge port (default: 8787)
  --worldosint-ws-interval MS    Poll interval in ms (default: 60000)
  --skip-worldosint-ws           Do not install the WorldOSINT headless WebSocket bridge agent
  --help                         Show this message
EOF
}

WORLDOSINT_ROOT="${WORLDOSINT_ROOT:-}"
MIROFISH_ROOT="${MIROFISH_ROOT:-}"
WORLDOSINT_BASE_URL="${WORLDOSINT_BASE_URL:-http://127.0.0.1:3000}"
WORLDOSINT_WS_PORT="${WORLDOSINT_WS_PORT:-8787}"
WORLDOSINT_WS_INTERVAL="${WORLDOSINT_WS_INTERVAL:-60000}"
INSTALL_WORLDOSINT_WS=1

while (($#)); do
  case "$1" in
    --worldosint-root)
      WORLDOSINT_ROOT="${2:-}"
      shift 2
      ;;
    --mirofish-root)
      MIROFISH_ROOT="${2:-}"
      shift 2
      ;;
    --worldosint-base-url)
      WORLDOSINT_BASE_URL="${2:-}"
      shift 2
      ;;
    --worldosint-ws-port)
      WORLDOSINT_WS_PORT="${2:-}"
      shift 2
      ;;
    --worldosint-ws-interval)
      WORLDOSINT_WS_INTERVAL="${2:-}"
      shift 2
      ;;
    --skip-worldosint-ws)
      INSTALL_WORLDOSINT_WS=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$WORLDOSINT_ROOT" || -z "$MIROFISH_ROOT" ]]; then
  echo "Both --worldosint-root and --mirofish-root are required." >&2
  usage >&2
  exit 1
fi

WORLDOSINT_ROOT="$(cd "$WORLDOSINT_ROOT" && pwd)"
MIROFISH_ROOT="$(cd "$MIROFISH_ROOT" && pwd)"

if [[ ! -f "$WORLDOSINT_ROOT/package.json" ]]; then
  echo "WorldOSINT root does not look valid: $WORLDOSINT_ROOT" >&2
  exit 1
fi

if [[ ! -f "$MIROFISH_ROOT/package.json" ]]; then
  echo "MiroFish root does not look valid: $MIROFISH_ROOT" >&2
  exit 1
fi

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/predihermes"
mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
USER_DOMAIN="gui/$(id -u)"

xml_escape() {
  printf '%s' "$1" | sed \
    -e 's/&/\&amp;/g' \
    -e 's/</\&lt;/g' \
    -e 's/>/\&gt;/g' \
    -e 's/"/\&quot;/g' \
    -e "s/'/\&apos;/g"
}

shell_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

write_plist() {
  local label="$1"
  local stdout_log="$2"
  local stderr_log="$3"
  local working_dir="$4"
  local command="$5"
  local plist_path="$LAUNCH_AGENTS_DIR/$label.plist"
  local xml_label xml_stdout xml_stderr xml_working_dir xml_command

  xml_label="$(xml_escape "$label")"
  xml_stdout="$(xml_escape "$stdout_log")"
  xml_stderr="$(xml_escape "$stderr_log")"
  xml_working_dir="$(xml_escape "$working_dir")"
  xml_command="$(xml_escape "$command")"

  cat >"$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$xml_label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>$xml_command</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>$xml_working_dir</string>
  <key>StandardOutPath</key>
  <string>$xml_stdout</string>
  <key>StandardErrorPath</key>
  <string>$xml_stderr</string>
</dict>
</plist>
EOF

  launchctl bootout "$USER_DOMAIN" "$plist_path" >/dev/null 2>&1 || true
  launchctl bootstrap "$USER_DOMAIN" "$plist_path"
  launchctl enable "$USER_DOMAIN/$label" >/dev/null 2>&1 || true
  launchctl kickstart -k "$USER_DOMAIN/$label"
  echo "Installed $label"
}

write_plist \
  "com.predihermes.worldosint" \
  "$LOG_DIR/worldosint.out.log" \
  "$LOG_DIR/worldosint.err.log" \
  "$WORLDOSINT_ROOT" \
  "cd $(shell_quote "$WORLDOSINT_ROOT") && npm run dev"

if [[ "$INSTALL_WORLDOSINT_WS" -eq 1 ]]; then
  write_plist \
    "com.predihermes.worldosint-ws" \
    "$LOG_DIR/worldosint-ws.out.log" \
    "$LOG_DIR/worldosint-ws.err.log" \
    "$WORLDOSINT_ROOT" \
    "cd $(shell_quote "$WORLDOSINT_ROOT") && npm run headless:ws -- --base $(shell_quote "$WORLDOSINT_BASE_URL") --port $(shell_quote "$WORLDOSINT_WS_PORT") --interval $(shell_quote "$WORLDOSINT_WS_INTERVAL") --allow-local 1"
fi

write_plist \
  "com.predihermes.mirofish-backend" \
  "$LOG_DIR/mirofish-backend.out.log" \
  "$LOG_DIR/mirofish-backend.err.log" \
  "$MIROFISH_ROOT" \
  "cd $(shell_quote "$MIROFISH_ROOT") && FLASK_DEBUG=False npm run backend"

echo
echo "LaunchAgents directory: $LAUNCH_AGENTS_DIR"
echo "Logs directory: $LOG_DIR"
echo "Loaded labels:"
echo "  com.predihermes.worldosint"
if [[ "$INSTALL_WORLDOSINT_WS" -eq 1 ]]; then
  echo "  com.predihermes.worldosint-ws"
fi
echo "  com.predihermes.mirofish-backend"
echo
echo "Useful commands:"
echo "  launchctl list | grep predihermes"
echo "  tail -f '$LOG_DIR/worldosint.out.log'"
echo "  tail -f '$LOG_DIR/mirofish-backend.out.log'"
