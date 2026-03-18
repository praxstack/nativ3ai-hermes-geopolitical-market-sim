#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./install.sh [options]

Core options:
  --bootstrap-stack         Clone/install WorldOSINT + MiroFish companions and generate launcher scripts
  --doctor                  Check host prerequisites and current PrediHermes installation state
  --with-launchd            Also install the optional PrediHermes launchd agents
  --help                    Show this message

Bootstrap options:
  --companion-dir PATH      Parent directory for companion repos (default: ~/predihermes/companions)
  --worldosint-root PATH    WorldOSINT checkout path (default: <companion-dir>/worldosint-headless)
  --mirofish-root PATH      MiroFish checkout path (default: <companion-dir>/MiroFish)
  --worldosint-url URL      Override WorldOSINT repo URL
  --mirofish-url URL        Override MiroFish repo URL
  --bin-dir PATH            Generated helper scripts dir (default: ~/predihermes/bin)
  --skip-worldosint-install Clone/reuse WorldOSINT but skip npm install
  --skip-mirofish-install   Clone/reuse MiroFish but skip dependency install
  --skip-hermes-env         Do not write WORLDOSINT_BASE_URL / MIROFISH_* entries into ~/.hermes/.env

Examples:
  ./install.sh
  ./install.sh --bootstrap-stack
  ./install.sh --bootstrap-stack --with-launchd
  ./install.sh --bootstrap-stack --companion-dir ~/predihermes/companions
USAGE
}

say() {
  printf '[PrediHermes] %s\n' "$*"
}

fail() {
  say "$*" >&2
  exit 1
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

normalize_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).expanduser().resolve())
PY
}

pip_install_requirements() {
  local python_bin="$1"
  local req_file="$2"
  "$python_bin" -m pip install --upgrade pip
  "$python_bin" -m pip install -r "$req_file"
}

write_script() {
  local path="$1"
  shift
  mkdir -p "$(dirname "$path")"
  cat > "$path"
  chmod +x "$path"
}

upsert_predihermes_env_block() {
  local env_file="$1"
  local mirofish_root="$2"
  local tmp
  tmp="$(mktemp)"
  if [[ -f "$env_file" ]]; then
    awk '
      BEGIN {skip = 0}
      /^# >>> PrediHermes >>>$/ {skip = 1; next}
      /^# <<< PrediHermes <<<$/{skip = 0; next}
      skip == 0 {print}
    ' "$env_file" > "$tmp"
  else
    : > "$tmp"
  fi

  cat >> "$tmp" <<ENV
# >>> PrediHermes >>>
WORLDOSINT_BASE_URL=http://127.0.0.1:3000
MIROFISH_BASE_URL=http://127.0.0.1:5001
MIROFISH_ROOT=$mirofish_root
# <<< PrediHermes <<<
ENV

  mv "$tmp" "$env_file"
}

clone_or_reuse_repo() {
  local label="$1"
  local url="$2"
  local root="$3"
  local sentinel="$4"

  if [[ -d "$root/.git" ]]; then
    say "Reusing $label checkout at $root"
  elif [[ -e "$root" ]]; then
    fail "$label path exists but is not a git checkout: $root"
  else
    mkdir -p "$(dirname "$root")"
    say "Cloning $label -> $root"
    git clone --depth 1 "$url" "$root"
  fi

  [[ -e "$root/$sentinel" ]] || fail "$label checkout at $root is missing $sentinel"
}

doctor() {
  local missing=0
  local companions_line="disabled"
  [[ "$BOOTSTRAP_STACK" -eq 1 ]] && companions_line="enabled"

  say "Doctor"
  for cmd in git python3; do
    if has_cmd "$cmd"; then
      printf 'OK   %s\n' "$cmd"
    else
      printf 'MISS %s\n' "$cmd"
      missing=1
    fi
  done

  for cmd in hermes npm node; do
    if has_cmd "$cmd"; then
      printf 'OK   %s\n' "$cmd"
    else
      printf 'WARN %s\n' "$cmd"
    fi
  done

  if has_cmd uv; then
    printf 'OK   uv\n'
  else
    printf 'INFO uv (backend will use backend/.venv fallback)\n'
  fi

  if [[ -d "$HERMES_HOME" ]]; then
    printf 'OK   hermes_home %s\n' "$HERMES_HOME"
  else
    printf 'WARN hermes_home %s\n' "$HERMES_HOME"
  fi

  if [[ -d "$DEST" ]]; then
    printf 'OK   installed_skill %s\n' "$DEST"
  else
    printf 'INFO installed_skill %s\n' "$DEST"
  fi

  printf 'INFO bootstrap_stack %s\n' "$companions_line"
  printf 'INFO worldosint_root %s\n' "$WORLDOSINT_ROOT"
  printf 'INFO mirofish_root %s\n' "$MIROFISH_ROOT"
  printf 'INFO helper_bin %s\n' "$BIN_DIR"

  return "$missing"
}

require_base_tools() {
  has_cmd git || fail "git is required"
  has_cmd python3 || fail "python3 is required"
}

require_hermes() {
  if has_cmd hermes; then
    return 0
  fi
  if [[ -d "$HERMES_HOME" ]]; then
    return 0
  fi
  fail "Hermes Agent is not installed. Install Hermes first, then rerun ./install.sh"
}

install_skill() {
  mkdir -p "$(dirname "$DEST")"
  rm -rf "$DEST"
  cp -R "$REPO_ROOT/skill/geopolitical-market-sim" "$DEST"
  python3 -m venv "$DEST/.venv"
  pip_install_requirements "$DEST/.venv/bin/python3" "$REPO_ROOT/requirements.txt"
  say "Installed skill to $DEST"
}

install_worldosint() {
  clone_or_reuse_repo "WorldOSINT" "$WORLDOSINT_URL" "$WORLDOSINT_ROOT" "package.json"
  if [[ "$SKIP_WORLDOSINT_INSTALL" -eq 0 ]]; then
    has_cmd npm || fail "npm is required to bootstrap WorldOSINT"
    has_cmd node || fail "node is required to bootstrap WorldOSINT"
    say "Installing WorldOSINT dependencies"
    (cd "$WORLDOSINT_ROOT" && npm install)
  else
    say "Skipping WorldOSINT dependency install"
  fi
}

install_mirofish() {
  clone_or_reuse_repo "MiroFish" "$MIROFISH_URL" "$MIROFISH_ROOT" "backend/requirements.txt"
  if [[ ! -f "$MIROFISH_ROOT/.env" && -f "$MIROFISH_ROOT/.env.example" ]]; then
    cp "$MIROFISH_ROOT/.env.example" "$MIROFISH_ROOT/.env"
    say "Created $MIROFISH_ROOT/.env from .env.example"
  fi

  if [[ "$SKIP_MIROFISH_INSTALL" -eq 0 ]]; then
    has_cmd npm || fail "npm is required to bootstrap MiroFish"
    has_cmd node || fail "node is required to bootstrap MiroFish"
    say "Installing MiroFish root dependencies"
    (cd "$MIROFISH_ROOT" && npm install)
    say "Installing MiroFish frontend dependencies"
    (cd "$MIROFISH_ROOT/frontend" && npm install)

    if has_cmd uv; then
      say "Syncing MiroFish backend with uv"
      (cd "$MIROFISH_ROOT/backend" && uv sync)
    else
      say "uv not found; using backend/.venv fallback"
      python3 -m venv "$MIROFISH_ROOT/backend/.venv"
      "$MIROFISH_ROOT/backend/.venv/bin/pip" install -r "$MIROFISH_ROOT/backend/requirements.txt"
    fi
  else
    say "Skipping MiroFish dependency install"
  fi
}

write_helper_launchers() {
  mkdir -p "$BIN_DIR"

  write_script "$BIN_DIR/predihermes" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
exec "$DEST/.venv/bin/python3" "$DEST/scripts/geopolitical_market_pipeline.py" "\$@"
SCRIPT

  write_script "$BIN_DIR/predihermes-worldosint" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
cd "$WORLDOSINT_ROOT"
exec npm run dev
SCRIPT

  write_script "$BIN_DIR/predihermes-worldosint-ws" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
BASE_URL="\${WORLDOSINT_BASE_URL:-http://127.0.0.1:3000}"
cd "$WORLDOSINT_ROOT"
exec npm run headless:ws -- --base "\$BASE_URL" --port 8787 --interval 60000 --allow-local 1
SCRIPT

  write_script "$BIN_DIR/predihermes-mirofish-backend" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
if command -v uv >/dev/null 2>&1; then
  cd "$MIROFISH_ROOT"
  exec env FLASK_DEBUG=False npm run backend
elif [[ -x "$MIROFISH_ROOT/backend/.venv/bin/python3" ]]; then
  cd "$MIROFISH_ROOT/backend"
  exec env FLASK_DEBUG=False ./\.venv/bin/python3 run.py
else
  cd "$MIROFISH_ROOT/backend"
  exec env FLASK_DEBUG=False python3 run.py
fi
SCRIPT

  write_script "$BIN_DIR/predihermes-mirofish-ui" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
cd "$MIROFISH_ROOT"
exec env MIROFISH_FRONTEND_PORT="\${MIROFISH_FRONTEND_PORT:-3001}" FLASK_DEBUG=False npm run frontend
SCRIPT

  write_script "$BIN_DIR/predihermes-stack-health" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
exec "$DEST/.venv/bin/python3" "$DEST/scripts/geopolitical_market_pipeline.py" health --mirofish-root "$MIROFISH_ROOT" "\$@"
SCRIPT

  say "Generated helper scripts in $BIN_DIR"
}

install_launchd_if_requested() {
  if [[ "$WITH_LAUNCHD" -eq 0 ]]; then
    return 0
  fi
  local have_worldosint_root=0
  local have_mirofish_root=0
  for arg in "${LAUNCHD_ARGS[@]}"; do
    [[ "$arg" == "--worldosint-root" ]] && have_worldosint_root=1
    [[ "$arg" == "--mirofish-root" ]] && have_mirofish_root=1
  done

  if [[ "$have_worldosint_root" -eq 0 ]]; then
    LAUNCHD_ARGS+=(--worldosint-root "$WORLDOSINT_ROOT")
  fi
  if [[ "$have_mirofish_root" -eq 0 ]]; then
    LAUNCHD_ARGS+=(--mirofish-root "$MIROFISH_ROOT")
  fi

  say "Installing optional launchd services"
  "$REPO_ROOT/launchd/install_launchd.sh" "${LAUNCHD_ARGS[@]}"
}

print_summary() {
  say "Setup complete"
  printf '\n'
  printf 'Skill path: %s\n' "$DEST"
  printf 'Helper bin: %s\n' "$BIN_DIR"
  if [[ "$BOOTSTRAP_STACK" -eq 1 ]]; then
    printf 'WorldOSINT: %s\n' "$WORLDOSINT_ROOT"
    printf 'MiroFish:   %s\n' "$MIROFISH_ROOT"
  fi
  printf '\n'
  printf 'Useful commands:\n'
  printf '  %s/predihermes health\n' "$BIN_DIR"
  if [[ "$BOOTSTRAP_STACK" -eq 1 ]]; then
    printf '  %s/predihermes-worldosint\n' "$BIN_DIR"
    printf '  %s/predihermes-worldosint-ws\n' "$BIN_DIR"
    printf '  %s/predihermes-mirofish-backend\n' "$BIN_DIR"
    printf '  %s/predihermes-mirofish-ui\n' "$BIN_DIR"
    printf '  %s/predihermes-stack-health\n' "$BIN_DIR"
  fi
  printf '  hermes -s geopolitical-market-sim\n'
  printf '\n'
  if [[ "$BOOTSTRAP_STACK" -eq 1 ]]; then
    printf 'Before running simulations, set MiroFish keys in %s/.env:\n' "$MIROFISH_ROOT"
    printf '  LLM_API_KEY\n'
    printf '  LLM_BASE_URL\n'
    printf '  LLM_MODEL_NAME\n'
    printf '  ZEP_API_KEY\n'
    printf '\n'
  fi
  printf 'If %s is not on PATH, run the commands with the full path shown above.\n' "$BIN_DIR"
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DEST="$HERMES_HOME/skills/research/geopolitical-market-sim"
STACK_HOME="${PREDIHERMES_HOME:-$HOME/predihermes}"
COMPANION_DIR="$STACK_HOME/companions"
BIN_DIR="$STACK_HOME/bin"
WORLDOSINT_URL="https://github.com/nativ3ai/worldosint-headless.git"
MIROFISH_URL="https://github.com/nativ3ai/MiroFish.git"
WORLDOSINT_ROOT="$COMPANION_DIR/worldosint-headless"
MIROFISH_ROOT="$COMPANION_DIR/MiroFish"
BOOTSTRAP_STACK=0
WITH_LAUNCHD=0
DOCTOR_ONLY=0
SKIP_HERMES_ENV=0
SKIP_WORLDOSINT_INSTALL=0
SKIP_MIROFISH_INSTALL=0
LAUNCHD_ARGS=()

while (($#)); do
  case "$1" in
    --bootstrap-stack)
      BOOTSTRAP_STACK=1
      ;;
    --with-launchd)
      WITH_LAUNCHD=1
      ;;
    --doctor)
      DOCTOR_ONLY=1
      ;;
    --companion-dir)
      shift
      [[ $# -gt 0 ]] || fail "--companion-dir requires a value"
      COMPANION_DIR="$1"
      WORLDOSINT_ROOT="$COMPANION_DIR/worldosint-headless"
      MIROFISH_ROOT="$COMPANION_DIR/MiroFish"
      ;;
    --worldosint-root)
      shift
      [[ $# -gt 0 ]] || fail "--worldosint-root requires a value"
      WORLDOSINT_ROOT="$1"
      ;;
    --mirofish-root)
      shift
      [[ $# -gt 0 ]] || fail "--mirofish-root requires a value"
      MIROFISH_ROOT="$1"
      ;;
    --worldosint-url)
      shift
      [[ $# -gt 0 ]] || fail "--worldosint-url requires a value"
      WORLDOSINT_URL="$1"
      ;;
    --mirofish-url)
      shift
      [[ $# -gt 0 ]] || fail "--mirofish-url requires a value"
      MIROFISH_URL="$1"
      ;;
    --bin-dir)
      shift
      [[ $# -gt 0 ]] || fail "--bin-dir requires a value"
      BIN_DIR="$1"
      ;;
    --skip-hermes-env)
      SKIP_HERMES_ENV=1
      ;;
    --skip-worldosint-install)
      SKIP_WORLDOSINT_INSTALL=1
      ;;
    --skip-mirofish-install)
      SKIP_MIROFISH_INSTALL=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      if [[ "$WITH_LAUNCHD" -eq 1 ]]; then
        LAUNCHD_ARGS+=("$1")
      else
        fail "Unknown option: $1"
      fi
      ;;
  esac
  shift
done

STACK_HOME="$(normalize_path "$STACK_HOME")"
COMPANION_DIR="$(normalize_path "$COMPANION_DIR")"
BIN_DIR="$(normalize_path "$BIN_DIR")"
WORLDOSINT_ROOT="$(normalize_path "$WORLDOSINT_ROOT")"
MIROFISH_ROOT="$(normalize_path "$MIROFISH_ROOT")"

if [[ "$DOCTOR_ONLY" -eq 1 ]]; then
  doctor
  exit $?
fi

require_base_tools
require_hermes
install_skill
write_helper_launchers

if [[ "$BOOTSTRAP_STACK" -eq 1 ]]; then
  install_worldosint
  install_mirofish
  if [[ "$SKIP_HERMES_ENV" -eq 0 ]]; then
    mkdir -p "$HERMES_HOME"
    upsert_predihermes_env_block "$HERMES_HOME/.env" "$MIROFISH_ROOT"
    say "Updated $HERMES_HOME/.env with local PrediHermes endpoints"
  else
    say "Skipping ~/.hermes/.env update"
  fi
fi

install_launchd_if_requested
print_summary
