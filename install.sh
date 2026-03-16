#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./install.sh [--with-launchd --worldosint-root /abs/path/worldosint-headless --mirofish-root /abs/path/MiroFish [launchd options]]

Options:
  --with-launchd   Also install the optional PrediHermes launchd agents
  --help           Show this message
EOF
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DEST="$HERMES_HOME/skills/research/geopolitical-market-sim"
WITH_LAUNCHD=0
LAUNCHD_ARGS=()

while (($#)); do
  case "$1" in
    --with-launchd)
      WITH_LAUNCHD=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      LAUNCHD_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ "$WITH_LAUNCHD" -eq 0 && "${#LAUNCHD_ARGS[@]}" -gt 0 ]]; then
  echo "launchd options require --with-launchd" >&2
  usage >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$REPO_ROOT/skill/geopolitical-market-sim" "$DEST"
python3 -m pip install -r "$REPO_ROOT/requirements.txt"
echo "Installed skill to $DEST"
echo "Next: export WORLDOSINT_BASE_URL / MIROFISH_BASE_URL / MIROFISH_ROOT as needed, then run:"
echo "  python3 \"$DEST/scripts/geopolitical_market_pipeline.py\" health"

if [[ "$WITH_LAUNCHD" -eq 1 ]]; then
  echo "Installing optional launchd services..."
  "$REPO_ROOT/launchd/install_launchd.sh" "${LAUNCHD_ARGS[@]}"
fi
