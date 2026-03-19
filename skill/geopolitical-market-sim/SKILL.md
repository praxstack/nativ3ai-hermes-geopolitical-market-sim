---
name: geopolitical-market-sim
description: PrediHermes, also named geopolitical-market-sim, tracks geopolitical topics, selects relevant open Polymarket contracts near deadline, generates MiroFish seed packets from WorldOSINT data, runs or inspects MiroFish simulations, and resolves historical branches or injected actors from local artifacts. Use this when the user wants PrediHermes, recurring geopolitical prediction-market monitoring, topic tracking, counterfactual actor injection, simulation comparison, or a local automation path from news + markets into MiroFish.
---

# PrediHermes

PrediHermes is the public name of the `geopolitical-market-sim` skill.

Use this skill for the local WorldOSINT -> Polymarket -> MiroFish workflow.

Helper script path:
`~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py`

Command policy:
- Prefer `predihermes <command> ...` if available on PATH.
- Fallback to `python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py <command> ...`.
- Do not stop after one failed shorthand attempt; retry with the full script path.
- If the local stack was bootstrapped, also prefer these helper launchers when you need services:
  - `~/predihermes/bin/predihermes-stack-up`
  - `~/predihermes/bin/predihermes-stack-status`
  - `~/predihermes/bin/predihermes-stack-health`
  - `~/predihermes/bin/predihermes-stack-down`

## What it does

- stores tracked geopolitical topics in `~/.hermes/data/geopolitical-market-sim/topics.json`
- fetches topic-relevant RSS/news from local WorldOSINT headless modules
- can attach topic-specific WorldOSINT module sets and module params
- searches open Polymarket markets, prefers near-deadline contracts, and pulls top-of-book pricing
- writes a MiroFish-ready seed packet and raw snapshot under `~/.hermes/data/geopolitical-market-sim/runs/...`
- optionally drives the full MiroFish API pipeline with moderate defaults
- supports MiroFish running either with the local SQLite graph backend or the Zep backend; do not assume Zep is present

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
If MiroFish uses `GRAPH_BACKEND=local`, that is valid and expected. Only ask for `ZEP_API_KEY` when the operator explicitly chose `GRAPH_BACKEND=zep`.

Backend selection rule:
- prefer local graph mode unless the user explicitly asks for Zep
- if the user says they want the cheaper/simpler local setup, use `GRAPH_BACKEND=local`
- if Zep returns quota/auth/availability errors, recommend switching MiroFish to `GRAPH_BACKEND=local` and restarting the backend
- do not block simulation work on missing `ZEP_API_KEY` if local graph mode is available
- only treat `ZEP_API_KEY` as required when `GRAPH_BACKEND=zep`

If health fails because the local services are not running and the helper launchers exist, bring them up with:

```bash
~/predihermes/bin/predihermes-stack-up
~/predihermes/bin/predihermes-stack-status
~/predihermes/bin/predihermes-stack-health
```

Use individual launchers only when the user explicitly wants one component started separately:

```bash
~/predihermes/bin/predihermes-worldosint
~/predihermes/bin/predihermes-worldosint-ws
~/predihermes/bin/predihermes-mirofish-backend
~/predihermes/bin/predihermes-mirofish-ui
```

When the user asks you to start or stop the stack from Hermes:

1. run `~/predihermes/bin/predihermes-stack-up` to start required services
2. run `~/predihermes/bin/predihermes-stack-status` to confirm tracked processes
3. run `~/predihermes/bin/predihermes-stack-health` to confirm the pipeline can talk to them
4. only then proceed with topic planning or simulation

If health fails because Zep is unavailable but the MiroFish backend can run locally:

1. inspect `~/predihermes/companions/MiroFish/.env`
2. if the operator did not explicitly require Zep, set `GRAPH_BACKEND=local`
3. restart the MiroFish backend
4. rerun `~/predihermes/bin/predihermes-stack-health`
5. continue with the pipeline once health passes

When the user asks to stop the local stack:

```bash
~/predihermes/bin/predihermes-stack-down
```

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

Before expensive runs, generate a plan and validate collected feeds:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  plan-tracked iran-conflict \
  --target-agents 48
```

The plan output includes:
- `feed_quality` (`good` / `moderate` / `poor`) with notes
- `simulation_plan` with selected rounds/profile parallelism and rationale

If the user wants strict safety before simulation, require feed confirmation:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  run-tracked iran-conflict \
  --simulate \
  --require-feed-confirmation
```

## Manage tracked topics

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py list-topics
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py untrack-topic <topic-id>
```

## Modular control for tracked topics

List available WorldOSINT modules first:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py list-worldosint-modules
```

Use `update-topic` to change modules and execution behavior without recreating the topic:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  update-topic iran-conflict \
  --add-headless-module military_naval \
  --set-module-param 'news_rss.max_total=160' \
  --set-platform parallel \
  --set-max-rounds 36
```

Useful modular flags:
- `--set-headless-module <module>` (repeatable): replace module set
- `--add-headless-module <module>` and `--remove-headless-module <module>`
- shorthand aliases also work: `--set-module`, `--add-module`, `--remove-module`
- `--set-module-param 'module.key=value'`
- `--remove-module-param module.key` or `--remove-module-param module`
- `--set-platform twitter|reddit|parallel`
- `--set-max-rounds <n>`
- `--set-simulation-mode auto|manual`
- `--set-target-agents <n>` (agent-count hint used for planning profile depth)

Per-run overrides:
- `--simulation-mode auto|manual`
- `--target-rounds <n>`
- `--target-agents <n>`
- `--require-feed-confirmation`

Natural Hermes ask patterns for module control:
- "Use PrediHermes and start the local stack, then tell me if WorldOSINT and MiroFish are healthy."
- "Use PrediHermes list-worldosint-modules and propose the best modules for Hormuz risk."
- "Use PrediHermes update-topic iran-conflict and add <module>, remove <module>, then show dashboard."
- "Use PrediHermes plan-tracked iran-conflict and confirm if feed quality is good enough."
- "Use PrediHermes run-tracked iran-conflict in manual mode with 36 rounds and 60 target agents."

Simulation planning behavior:
- If user gives explicit rounds/agents, run in manual mode and follow those values.
- If user asks the agent to decide, use auto mode with feed quality.
- If user gives neither, ask concise clarifiers:
  - auto vs manual mode
  - optional rounds and/or agent-count target

## How to use the output

After a run:
- read `run_summary.md`
- if simulation ran, read `simulation_summary.md`
- use the selected primary contract question and description as the resolution anchor
- separate these clearly in your answer:
  - current market price / bid-ask
- simulation-derived directional view
- what evidence would change the call

## Hermes CLI dashboard and command awareness

PrediHermes can print a terminal-native ASCII dashboard so users see pipeline status directly in Hermes:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py dashboard --topic-id iran-conflict
```

This dashboard shows:
- primary market bid/ask/deadline
- OSINT signal counts (headlines, theme, risk summary, modules)
- simulation status/action totals when simulation artifacts exist

To show command awareness/help for users inside Hermes:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py command-catalog
```

When responding in Hermes, if a user asks “what can PrediHermes do next?”, use `command-catalog` and then suggest 1-2 relevant next commands.

Do not invent exact resolution criteria if the market description is vague. Say when the market page needs manual verification.

## Simulation and actor retrieval

When the user mentions a simulation, branch, or injected actor, do not start with Hermes `recall`. These runs live in local MiroFish artifacts, not necessarily in Hermes memory.

Use the helper script first:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  lookup-sim \
  --simulation-id sim_b48c23571420
```

Search by actor name:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  lookup-sim \
  --actor "Shadow Hormuz Underwriter"
```

Search by loose query:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  lookup-sim \
  --query "hormuz actor branch"
```

Use `--counterfactual-only` when the user clearly means an injected-actor branch.
If MiroFish is not at the default path, add `--mirofish-root /absolute/path/to/MiroFish`.
If omitted, the helper will try the current working directory, `~/Downloads/MiroFish-main`, and `~/MiroFish-main`.

What `lookup-sim` returns:
- matching `simulation_id` values
- base/branch relationship for counterfactual runs
- injected actor metadata with `agent_id` and `injection_round`
- artifact paths for `simulation_config.json`, `state.json`, and action logs

Recommended workflow for simulation questions:
1. run `lookup-sim`
2. read the returned artifact paths with `terminal`
3. only use `recall` if the user explicitly asks about prior Hermes chat context rather than the simulation artifacts

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
- if asked to create any artifact, verify it exists before claiming success
- for files use `test -f` or `stat`; for media also use `ffprobe` and report duration/size
- if verification fails, say the artifact was not produced instead of summarizing an imaginary result

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
