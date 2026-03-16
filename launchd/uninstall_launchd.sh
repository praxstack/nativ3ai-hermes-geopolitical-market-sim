#!/usr/bin/env bash
set -euo pipefail

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
USER_DOMAIN="gui/$(id -u)"
LABELS=(
  "com.predihermes.worldosint"
  "com.predihermes.worldosint-ws"
  "com.predihermes.mirofish-backend"
)

for label in "${LABELS[@]}"; do
  plist_path="$LAUNCH_AGENTS_DIR/$label.plist"
  launchctl bootout "$USER_DOMAIN" "$plist_path" >/dev/null 2>&1 || true
  rm -f "$plist_path"
  echo "Removed $label"
done

echo "PrediHermes launchd agents removed."
