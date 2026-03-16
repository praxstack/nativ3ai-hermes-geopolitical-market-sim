---
name: geopolitical-market-sim
description: Track geopolitical topics, select relevant open Polymarket contracts near deadline, generate MiroFish seed packets from WorldOSINT data, and optionally run the MiroFish simulation pipeline. Use this when the user wants recurring geopolitical prediction-market monitoring, topic tracking, or a local automation path from news + markets into MiroFish.
---

# Geopolitical Market Sim

Use this skill for the local WorldOSINT -> Polymarket -> MiroFish workflow.

Helper script path:
`~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py`

## What it does

- stores tracked geopolitical topics in `~/.hermes/data/geopolitical-market-sim/topics.json`
- fetches topic-relevant RSS/news from local WorldOSINT headless modules
- can attach topic-specific WorldOSINT module sets and module params
- searches open Polymarket markets, prefers near-deadline contracts, and pulls top-of-book pricing
- writes a MiroFish-ready seed packet and raw snapshot under `~/.hermes/data/geopolitical-market-sim/runs/...`
- optionally drives the full MiroFish API pipeline with moderate defaults

Treat Iran as an example, not a built-in assumption. This skill is meant for reusable tracked topics.

## Default operating mode

Use moderate settings unless the user asks otherwise:
- `platform=parallel`
- `max_rounds=24`
- `use_llm_for_profiles=false`
- `enable_graph_memory_update=false`
- do not generate the MiroFish report unless the user asks

## First checks

Run health before first use or when failures look environmental:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py health
```

If `MiroFish` is down, do not claim the simulation ran. If `WorldOSINT` is down, do not claim the packet is current.

## Track a topic

Decide these fields up front:
- `topic_id`: stable slug for scheduling and retrieval
- `topic`: the event class or forecast theme
- `market_query`: what to search on Polymarket
- `keyword`: terms that should survive RSS filtering
- `headless_module`: which WorldOSINT modules matter for this topic
- `module_param`: optional per-module overrides

If the user does not specify modules, use:
- `news_rss`
- `intelligence_risk_scores`
- `military_usni`

Generic pattern:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  track-topic \
  --topic-id <topic-id> \
  --topic "<topic>" \
  --market-query "<market query>" \
  --keyword <term1> --keyword <term2> \
  --headless-module news_rss
```

Custom module params use either:
- `--module-param 'news_rss.max_total=120'`
- `--module-param 'news_rss={\"max_total\":120,\"limit_per_feed\":15}'`

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

## Run ad hoc without saving

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  run-topic \
  --topic "Iran conflict and nuclear diplomacy" \
  --market-query "Iran nuclear deal" \
  --keyword iran --keyword israel --keyword hormuz --keyword nuclear --keyword enrichment --keyword iaea \
  --simulate
```

Use `run-topic` for one-off questions and `track-topic` plus `run-tracked` for scheduled workflows.

## Run a tracked topic

Seed packet only:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  run-tracked iran-conflict
```

Seed packet plus MiroFish simulation:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  run-tracked iran-conflict \
  --simulate
```

## Manage tracked topics

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py list-topics
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py untrack-topic <topic-id>
```

## How to use the output

After a run:
- read `run_summary.md`
- if simulation ran, read `simulation_summary.md`
- use the selected primary contract question and description as the resolution anchor
- separate these clearly in your answer:
  - current market price / bid-ask
  - simulation-derived directional view
  - what evidence would change the call

Do not invent exact resolution criteria if the market description is vague. Say when the market page needs manual verification.

## Counterfactual actor injection

If the user wants to test how a new actor would change a past simulation, use the MiroFish backend headlessly. Do not require the UI.

Prerequisites:
- MiroFish backend must be running on `MIROFISH_BASE_URL` and should expose `POST /api/simulation/<base_simulation_id>/counterfactual`
- the base simulation must already exist

Workflow:
1. choose the historical `simulation_id`
2. create a counterfactual branch by posting actor data plus `injection_round`
3. read the returned branch `simulation_id`
4. start the new branch with the normal `/api/simulation/start` call
5. poll `run-status`, `run-status/detail`, `timeline`, and `actions` like any other simulation

Recommended use:
- inject one actor at a time
- choose the injection round from a historically important or high-action round
- provide an `opening_statement` only if the user explicitly wants the actor to announce itself at insertion time

Example branch creation:

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

Then start it:

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

Monitoring endpoints:
- `GET /api/simulation/<id>/run-status`
- `GET /api/simulation/<id>/run-status/detail`
- `GET /api/simulation/<id>/timeline`
- `GET /api/simulation/<id>/actions?round_num=<n>`

When answering the user:
- clearly separate the base run from the counterfactual branch
- state the injected actor, stance, and injection round
- avoid claiming the branch is a replay of history; it is a new simulation seeded from the old one
- if the endpoint is unavailable, say the local MiroFish backend needs the counterfactual-capable fork

## Cron usage

Attach this skill to the Hermes cron job and make the prompt explicit. Keep the prompt self-contained.

Good cron prompt pattern:
- run the tracked topic by id
- if simulation succeeds, read the generated summaries
- return one final forecast for the primary market with concise reasons
- mention artifact paths in the final response

Example job intent:
- "Run the tracked topic `iran-conflict`. If the simulation succeeds, read the generated summaries and give a final YES/NO call for the primary market with 3-5 reasons. Mention the artifact paths."
- "Run the tracked topic `<topic-id>`. Read the newest `run_summary.md` and `simulation_summary.md`. Return the primary market, current bid/ask, directional call, why the simulation leans that way, and the artifact paths."

Use one tracked topic per cron job. That keeps scheduling clean, lets Hermes answer about each topic independently, and avoids mixing different market resolution criteria in one run.
