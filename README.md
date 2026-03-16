# PrediHermes

PrediHermes is a Hermes skill for end-to-end geopolitical market forecasting:

- WorldOSINT headless modules for OSINT signals
- Polymarket Gamma/CLOB for open-market discovery and pricing
- MiroFish for multi-agent simulation and counterfactual branches
- Hermes chat + cron for operator workflows and scheduling

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Companion Repos](#companion-repos)
- [1) Start WorldOSINT](#1-start-worldosint)
- [2) Start MiroFish](#2-start-mirofish)
- [3) Install PrediHermes Skill](#3-install-predihermes-skill)
- [4) Configure Hermes Model and API Key](#4-configure-hermes-model-and-api-key)
- [5) Optional `predihermes` CLI Alias](#5-optional-predihermes-cli-alias)
- [6) Verify End-to-End](#6-verify-end-to-end)
- [7) Track and Run Topics](#7-track-and-run-topics)
- [8) Use from Hermes Chat](#8-use-from-hermes-chat)
- [9) Schedule Runs](#9-schedule-runs)
- [10) Counterfactual Injection](#10-counterfactual-injection)
- [Optional macOS `launchd` Add-On](#optional-macos-launchd-add-on)
- [Troubleshooting](#troubleshooting)
- [Repository Layout](#repository-layout)

## Architecture

```text
WorldOSINT headless -> PrediHermes pipeline -> Polymarket selection -> seed packet/snapshot
                                                          |
                                                          v
                                                     MiroFish run
                                                          |
                                                          v
                                                Hermes summary / cron
```

## Prerequisites

- Hermes Agent installed and working (`hermes --help`)
- Python 3.10+
- Node.js 18+
- Local or remote WorldOSINT endpoint
- Local or remote MiroFish endpoint (required for `--simulate`)

## Companion Repos

- WorldOSINT headless: https://github.com/nativ3ai/worldosint-headless
- MiroFish fork used for this workflow: https://github.com/nativ3ai/MiroFish

This skill is documented and validated against the `nativ3ai` repos above.

## 1) Start WorldOSINT

```bash
git clone https://github.com/nativ3ai/worldosint-headless.git
cd worldosint-headless
npm install
npm run dev
```

Default base URL:

- `http://127.0.0.1:3000`

Check module catalog:

```bash
curl "http://127.0.0.1:3000/api/headless?module=list&format=json"
```

Optional websocket bridge:

```bash
npm run headless:ws -- --base http://127.0.0.1:3000 --port 8787 --interval 60000 --allow-local 1
```

## 2) Start MiroFish

```bash
git clone https://github.com/nativ3ai/MiroFish.git
cd MiroFish
cp .env.example .env
```

Set required `.env` values for MiroFish:

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `ZEP_API_KEY`

Install and run backend:

```bash
npm install
cd frontend && npm install && cd ..
cd backend && uv sync && cd ..
FLASK_DEBUG=False npm run backend
```

Default API:

- `http://127.0.0.1:5001`

Health:

```bash
curl "http://127.0.0.1:5001/health"
```

Optional UI:

```bash
MIROFISH_FRONTEND_PORT=3001 FLASK_DEBUG=False npm run dev
```

## 3) Install PrediHermes Skill

### Recommended (repo installer)

```bash
git clone https://github.com/nativ3ai/hermes-geopolitical-market-sim.git
cd hermes-geopolitical-market-sim
./install.sh
```

This installs to:

- `~/.hermes/skills/research/geopolitical-market-sim`

### Install with optional launchd in one command

```bash
./install.sh --with-launchd \
  --worldosint-root /absolute/path/to/worldosint-headless \
  --mirofish-root /absolute/path/to/MiroFish
```

## 4) Configure Hermes Model and API Key

Set Hermes to OpenAI Codex provider with your preferred model:

```bash
hermes config set model.provider openai-codex
hermes config set model.default gpt-5.3-codex-medium
hermes config set model.base_url https://api.openai.com/v1
```

Put your key in:

- `~/.hermes/.env`

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
```

## 5) Optional `predihermes` CLI Alias

The skill works with full script path by default. For shorter commands, add:

```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/predihermes <<'SH'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$HOME/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py"
exec python3 "$SCRIPT" "$@"
SH
chmod +x ~/.local/bin/predihermes
```

Ensure `~/.local/bin` is in `PATH`.

## 6) Verify End-to-End

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py health
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py list-worldosint-modules
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py command-catalog
```

If you created the alias:

```bash
predihermes health
predihermes list-worldosint-modules
predihermes command-catalog
```

## 7) Track and Run Topics

Track topic:

```bash
predihermes track-topic \
  --topic-id iran-conflict \
  --topic "Iran conflict and nuclear diplomacy" \
  --market-query "Iran nuclear deal" \
  --keyword iran --keyword israel --keyword hormuz --keyword nuclear --keyword enrichment --keyword iaea \
  --region-code IR --region-code IL --region-code SA --region-code US
```

Run tracked topic (seed only):

```bash
predihermes run-tracked iran-conflict
```

Run tracked topic with simulation:

```bash
predihermes run-tracked iran-conflict --simulate
```

Show ASCII dashboard:

```bash
predihermes dashboard iran-conflict
```

Modular control examples:

```bash
predihermes list-worldosint-modules
predihermes update-topic iran-conflict --add-module maritime_snapshot
predihermes update-topic iran-conflict --remove-module maritime_snapshot
predihermes update-topic iran-conflict --set-max-rounds 28
```

## 8) Use from Hermes Chat

Start with skill loaded:

```bash
hermes -s geopolitical-market-sim
```

Natural prompts:

- `Use PrediHermes list-worldosint-modules and suggest 6 modules for maritime risk.`
- `Use PrediHermes update-topic iran-conflict: add module maritime_snapshot and set max rounds to 28.`
- `Use PrediHermes run-tracked iran-conflict with simulate and summarize implied vs forecast.`
- `Use PrediHermes dashboard iran-conflict and summarize top drift signals.`

## 9) Schedule Runs

Daily scheduled run:

```bash
hermes cron create 'every 1d' \
  "Using the terminal tool, run: predihermes run-tracked iran-conflict --simulate. Then read run_summary.md and simulation_summary.md and return market question, yes bid/ask, directional call, reasons, and artifact paths." \
  --skill geopolitical-market-sim \
  --name 'Iran Conflict Market Sim' \
  --deliver local
```

## 10) Counterfactual Injection

Create branch from base simulation:

```bash
curl -X POST http://127.0.0.1:5001/api/simulation/<base_simulation_id>/counterfactual \
  -H 'Content-Type: application/json' \
  -d '{
    "actor": {
      "name": "Swiss backchannel envoy",
      "entity_type": "Diplomat",
      "profession": "Diplomat",
      "country": "Switzerland",
      "stance": "mediator",
      "bio": "Quiet envoy coordinating verification-first diplomacy.",
      "persona": "Prioritizes de-escalation, inspections, and sequencing.",
      "interested_topics": ["backchannel diplomacy", "IAEA inspections"],
      "activity_level": 0.55,
      "influence_weight": 3.4,
      "posts_per_hour": 1.2,
      "comments_per_hour": 0.9,
      "active_hours": [8,9,10,11,12,13,14,15,16,17,18]
    },
    "injection_round": 12,
    "opening_statement": "Verification-first sequencing is the only viable path."
  }'
```

Start branch:

```bash
curl -X POST http://127.0.0.1:5001/api/simulation/start \
  -H 'Content-Type: application/json' \
  -d '{
    "simulation_id": "<new_simulation_id>",
    "platform": "parallel",
    "force": true,
    "enable_graph_memory_update": true
  }'
```

Monitor:

- `GET /api/simulation/<id>/run-status`
- `GET /api/simulation/<id>/run-status/detail`
- `GET /api/simulation/<id>/timeline`
- `GET /api/simulation/<id>/actions?round_num=<n>`

## Optional macOS `launchd` Add-On

Install agents:

```bash
./launchd/install_launchd.sh \
  --worldosint-root /absolute/path/to/worldosint-headless \
  --mirofish-root /absolute/path/to/MiroFish
```

Installed labels:

- `com.predihermes.worldosint`
- `com.predihermes.worldosint-ws` (optional)
- `com.predihermes.mirofish-backend`

Checks:

```bash
launchctl list | grep predihermes
tail -f ~/Library/Logs/predihermes/worldosint.out.log
tail -f ~/Library/Logs/predihermes/mirofish-backend.out.log
```

Uninstall:

```bash
./launchd/uninstall_launchd.sh
```

## Troubleshooting

- `Unknown provider 'openai'` in Hermes:
  - set `model.provider` to `openai-codex` (not `openai`)
- `predihermes: command not found`:
  - use full script path or add alias in Section 5
- Health fails for WorldOSINT/MiroFish:
  - verify both services are up and URLs match your env
- Status mismatches across simulations:
  - compare both `state.json` and `run_state.json`; older runs may contain stale status fields

Artifact truth rule:

- Do not claim files/reports/media exist until verified.
- Use `test -f` or `stat` for files and `ffprobe` for media duration/size.

## Repository Layout

- `skill/geopolitical-market-sim/SKILL.md`
- `skill/geopolitical-market-sim/agents/openai.yaml`
- `skill/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py`
- `install.sh`
- `launchd/install_launchd.sh`
- `launchd/uninstall_launchd.sh`
