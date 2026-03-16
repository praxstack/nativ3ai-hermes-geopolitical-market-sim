# PrediHermes

PrediHermes is a plug-and-play Hermes skill for geopolitical prediction workflows.

It combines:
- WorldOSINT headless modules for OSINT snapshots, RSS monitoring, and topic-specific signals
- Polymarket Gamma/CLOB for open market selection and live yes bid/ask data
- MiroFish for graph-backed social simulation
- Hermes cron jobs for scheduled recurring forecasts
- optional `launchd` helpers for local macOS deployment

## What it does

The skill installs a local command workflow that can:
- track geopolitical topics with persistent topic configs
- fetch WorldOSINT headless data with topic-specific module sets
- select open Polymarket contracts near deadline with clear resolution wording
- generate MiroFish-ready seed packets and raw snapshots
- optionally run the full MiroFish simulation pipeline
- write run summaries Hermes can read back in normal chat or scheduled jobs

The pipeline is not Iran-specific. A tracked topic can represent:
- a conflict escalation market
- an election outcome market
- a sanctions or tariff deadline
- a ceasefire or nuclear-deal question
- a shipping, energy, cyber, or aviation disruption market

## Counterfactual Branching

PrediHermes can also drive the MiroFish counterfactual branch flow headlessly.

That means Hermes can:
- pick an existing historical `simulation_id`
- inject a new actor with a chosen role, stance, persona, and active-hours profile
- choose the exact `injection_round`
- optionally give that actor an opening statement at insertion time
- launch the branch as a new MiroFish simulation and compare it against the base run

This is intended for questions like:
- "What if a serious mediator appeared in round 12?"
- "How would a hawkish government spokesperson change the discourse?"
- "What if a market-native analyst account entered midway through the cycle?"

Headless API flow:

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
      "persona": "Prioritizes de-escalation, inspection sequencing, and face-saving language for both sides.",
      "interested_topics": ["backchannel diplomacy", "IAEA inspections", "sanctions relief"],
      "activity_level": 0.55,
      "influence_weight": 3.4,
      "posts_per_hour": 1.2,
      "comments_per_hour": 0.9,
      "active_hours": [8,9,10,11,12,13,14,15,16,17,18]
    },
    "injection_round": 12,
    "opening_statement": "Swiss channel update: verification-first sequencing is the only viable path."
  }'
```

Then start the returned branch:

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

Monitor like any other MiroFish run:
- `GET /api/simulation/<id>/run-status`
- `GET /api/simulation/<id>/run-status/detail`
- `GET /api/simulation/<id>/timeline`
- `GET /api/simulation/<id>/actions?round_num=<n>`

Important:
- this is a new branch simulation, not a replay of the historical run
- the capability depends on the counterfactual-capable `nativ3ai/MiroFish` fork

To inspect the current WorldOSINT headless catalog on your own deployment:

```bash
curl 'http://127.0.0.1:3000/api/headless?module=list&format=json'
```

## Requirements

- Hermes Agent installed and working
- Python 3.10+
- WorldOSINT running locally or remotely
- MiroFish running locally or remotely if you want simulation execution

Recommended local defaults:
- `WORLDOSINT_BASE_URL=http://127.0.0.1:3000`
- `MIROFISH_BASE_URL=http://127.0.0.1:5001`
- `MIROFISH_ROOT=/absolute/path/to/MiroFish`

## Companion Repos

This skill depends on two companion projects:

- WorldOSINT headless: https://github.com/nativ3ai/worldosint-headless
- MiroFish fork used for this workflow: https://github.com/nativ3ai/MiroFish

Reference links:
- MiroFish upstream: https://github.com/666ghj/MiroFish
- MiroFish patch PR for the Zep hardening used here: https://github.com/666ghj/MiroFish/pull/204

Use the `nativ3ai/MiroFish` fork if you want the exact behavior this skill was validated against.

## End-to-End Setup

### 1. Start WorldOSINT

```bash
git clone https://github.com/nativ3ai/worldosint-headless.git
cd worldosint-headless
npm install
npm run dev
```

Expected local base:
- `http://127.0.0.1:3000`

Health / discovery check:

```bash
curl "http://127.0.0.1:3000/api/headless?module=list&format=json"
```

Optional WebSocket bridge for local polling and alert workflows:

```bash
npm run headless:ws -- --base http://127.0.0.1:3000 --port 8787 --interval 60000 --allow-local 1
```

### 2. Start MiroFish

```bash
git clone https://github.com/nativ3ai/MiroFish.git
cd MiroFish
cp .env.example .env
```

Fill `.env` with your provider keys, including:
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `ZEP_API_KEY`

Install dependencies:

```bash
npm install
cd frontend && npm install && cd ..
cd backend && uv sync && cd ..
```

Start the backend headlessly:

```bash
FLASK_DEBUG=False npm run backend
```

Expected local API:
- `http://127.0.0.1:5001`

Health check:

```bash
curl "http://127.0.0.1:5001/health"
```

Optional UI:

```bash
MIROFISH_FRONTEND_PORT=3001 FLASK_DEBUG=False npm run dev
```

### 3. Install This Hermes Skill

```bash
git clone https://github.com/nativ3ai/hermes-geopolitical-market-sim.git
cd hermes-geopolitical-market-sim
./install.sh
```

At that point the default local wiring is:
- WorldOSINT: `http://127.0.0.1:3000`
- MiroFish API: `http://127.0.0.1:5001`
- Hermes skill data: `~/.hermes/data/geopolitical-market-sim`

### 4. Optional `launchd` Add-On

PrediHermes now ships an optional `launchd` installer for macOS. It is not forced.

Manual service install:

```bash
./launchd/install_launchd.sh \
  --worldosint-root /absolute/path/to/worldosint-headless \
  --mirofish-root /absolute/path/to/MiroFish
```

One-shot install plus services:

```bash
./install.sh --with-launchd \
  --worldosint-root /absolute/path/to/worldosint-headless \
  --mirofish-root /absolute/path/to/MiroFish
```

What it installs:
- `com.predihermes.worldosint`
- `com.predihermes.worldosint-ws`
- `com.predihermes.mirofish-backend`

The WebSocket bridge is optional. Skip it with:

```bash
./launchd/install_launchd.sh \
  --worldosint-root /absolute/path/to/worldosint-headless \
  --mirofish-root /absolute/path/to/MiroFish \
  --skip-worldosint-ws
```

Useful checks:

```bash
launchctl list | grep predihermes
tail -f ~/Library/Logs/predihermes/worldosint.out.log
tail -f ~/Library/Logs/predihermes/mirofish-backend.out.log
```

Remove the agents:

```bash
./launchd/uninstall_launchd.sh
```

You can still run everything manually if you do not want `launchd`.

## Install

```bash
git clone https://github.com/nativ3ai/hermes-geopolitical-market-sim.git
cd hermes-geopolitical-market-sim
./install.sh
```

This copies the skill to:
- `~/.hermes/skills/research/geopolitical-market-sim`

It also installs the Python dependency used by the helper script.

Optional service install:

```bash
./install.sh --with-launchd \
  --worldosint-root /absolute/path/to/worldosint-headless \
  --mirofish-root /absolute/path/to/MiroFish
```

## Health Check

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py health
```

## Track a Topic

Each topic stores:
- `topic_id`: stable key for Hermes and cron
- `topic`: human-readable event or market theme
- `market_query`: Polymarket search string
- `keyword`: RSS/news filters
- `region_code` and `theater_region`: optional risk/posture filters
- `headless_module`: WorldOSINT modules to include for this topic
- `module_param`: per-module overrides in `module.key=value` or `module={"key":"value"}` form

If you do not pass `--headless-module`, the script uses:
- `news_rss`
- `intelligence_risk_scores`
- `military_usni`

Generic template:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  track-topic \
  --topic-id <topic-id> \
  --topic "<topic name>" \
  --market-query "<polymarket search query>" \
  --keyword <keyword1> --keyword <keyword2> \
  --region-code <CC> \
  --theater-region "<region name>" \
  --headless-module news_rss \
  --headless-module intelligence_risk_scores \
  --headless-module military_usni
```

Iran example:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  track-topic \
  --topic-id iran-conflict \
  --topic "Iran conflict and nuclear diplomacy" \
  --market-query "Iran nuclear deal" \
  --keyword iran --keyword israel --keyword hormuz --keyword nuclear --keyword enrichment --keyword iaea \
  --region-code IR --region-code IL --region-code SA --region-code US \
  --theater-region "Persian Gulf" \
  --theater-region "Arabian Sea" \
  --theater-region "Red Sea" \
  --theater-region "Eastern Mediterranean Sea"
```

Taiwan Strait example:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  track-topic \
  --topic-id taiwan-strait \
  --topic "Taiwan Strait crisis and military signaling" \
  --market-query "Taiwan China blockade invasion" \
  --keyword taiwan --keyword china --keyword pla --keyword blockade --keyword exercise \
  --region-code TW --region-code CN --region-code US \
  --theater-region "South China Sea" \
  --theater-region "Philippine Sea" \
  --headless-module news_rss \
  --headless-module intelligence_risk_scores \
  --headless-module military_usni
```

Election example with custom WorldOSINT module params:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  track-topic \
  --topic-id south-korea-election \
  --topic "South Korea presidential election" \
  --market-query "South Korea election" \
  --keyword south --keyword korea --keyword election --keyword poll \
  --headless-module news_rss \
  --module-param 'news_rss.max_total=120' \
  --module-param 'news_rss.limit_per_feed=15'
```

Shipping or aviation example with extra WorldOSINT modules:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  track-topic \
  --topic-id red-sea-shipping \
  --topic "Red Sea shipping disruption" \
  --market-query "Red Sea shipping Hormuz tanker" \
  --keyword red --keyword sea --keyword shipping --keyword tanker --keyword vessel \
  --headless-module news_rss \
  --headless-module intelligence_risk_scores \
  --headless-module military_usni \
  --headless-module military_flights \
  --headless-module maritime_snapshot \
  --headless-module supply_chain_shipping
```

## Manage Topics

List everything Hermes is tracking:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py list-topics
```

Remove a topic you no longer want scheduled:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py untrack-topic red-sea-shipping
```

## Run a Topic

Seed packet only:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py run-tracked iran-conflict
```

Seed packet plus MiroFish simulation:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py run-tracked iran-conflict --simulate
```

Ad hoc topic without saving it first:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  run-topic \
  --topic "Gaza ceasefire negotiations" \
  --market-query "Gaza ceasefire" \
  --keyword gaza --keyword ceasefire --keyword hostage --keyword qatar \
  --simulate
```

## Use from Hermes Chat

```bash
hermes -s geopolitical-market-sim
```

Example prompts:
- `List my tracked geopolitical topics and tell me which ones have daily schedules.`
- `Run the tracked topic taiwan-strait now and summarize the market.`
- `Read the latest run_summary.md and simulation_summary.md for south-korea-election and give the forecast.`
- `Track a new sanctions topic for Russia energy exports and schedule it every 12 hours.`
- `List my tracked geopolitical topics.`

## Schedule Forecasts

Generic daily pattern:

```bash
hermes cron create 'every 1d' \
  "Using the terminal tool, run: python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py run-tracked <topic-id> --simulate. Then read the generated run_summary.md and simulation_summary.md from the run directory and return a concise forecast for the primary market with the market question, current yes bid/ask, simulation directional call, 3-5 reasons, and artifact paths." \
  --skill geopolitical-market-sim \
  --name '<Topic Name> Market Sim' \
  --deliver local
```

Iran example:

```bash
hermes cron create 'every 1d' \
  "Using the terminal tool, run: python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py run-tracked iran-conflict --simulate. Then read the generated run_summary.md and simulation_summary.md from the run directory and return a concise forecast for the primary market with the market question, current yes bid/ask, simulation directional call, 3-5 reasons, and artifact paths." \
  --skill geopolitical-market-sim \
  --name 'Iran Conflict Market Sim' \
  --deliver local
```

Faster intraday cycle:

```bash
hermes cron create 'every 6h' \
  "Using the terminal tool, run: python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py run-tracked taiwan-strait --simulate. Then read the latest run_summary.md and simulation_summary.md and return the primary market, current bid/ask, directional call, reasons, and paths." \
  --skill geopolitical-market-sim \
  --name 'Taiwan Strait Market Sim' \
  --deliver local
```

You can create one cron job per topic. Hermes stores the topic definitions separately from the schedules, so you can run the same tracked event on different cadences if needed.

Make sure the Hermes gateway service is running so cron jobs fire.

## Configuration Notes

The helper script reads these environment variables if present:
- `WORLDOSINT_BASE_URL`
- `MIROFISH_BASE_URL`
- `MIROFISH_ROOT`
- `HERMES_HOME`

No API keys are stored in this repo. Configure provider keys through your normal Hermes or MiroFish environment.

## Repo Layout

- `skill/geopolitical-market-sim/SKILL.md`
- `skill/geopolitical-market-sim/agents/openai.yaml`
- `skill/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py`
- `install.sh`
- `launchd/install_launchd.sh`
- `launchd/uninstall_launchd.sh`
