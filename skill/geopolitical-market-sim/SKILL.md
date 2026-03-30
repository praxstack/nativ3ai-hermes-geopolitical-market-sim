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

## What it does

- stores tracked geopolitical topics in `~/.hermes/data/geopolitical-market-sim/topics.json`
- fetches topic-relevant RSS/news from local WorldOSINT headless modules
- can attach topic-specific WorldOSINT module sets and module params
- searches open Polymarket markets, prefers near-deadline contracts, and pulls top-of-book pricing
- writes a MiroFish-ready seed packet and raw snapshot under `~/.hermes/data/geopolitical-market-sim/runs/...`
- writes a cleaner `simulation_brief.md` per run for graph construction, so local extraction sees the evidence instead of dashboard metadata
- optionally drives the full MiroFish API pipeline with moderate defaults

Treat Iran as an example, not a built-in assumption. This skill is meant for reusable tracked topics.

## Default operating mode

Use moderate settings unless the user asks otherwise:
- `platform=parallel`
- `max_rounds=24`
- `use_llm_for_profiles=false`
- `enable_graph_memory_update=false`
- do not generate the MiroFish report unless the user asks

Keep cast generation deterministic and local by default. Do not use Hermes as the per-round actor engine or as the default cast generator. The right split is:
- local model / rule-based defaults create the cast
- operator overrides come from a profile manifest when manual steering is needed

## First checks

Run health before first use or when failures look environmental:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py health
```

If `MiroFish` is down, do not claim the simulation ran. If `WorldOSINT` is down, do not claim the packet is current.
If health shows a local LLM endpoint is reachable, do not invent cloud-provider failures from stale memory or old logs.
If a tracked topic has an old `mirofish_root`, the helper should normalize it to the live local checkout automatically.

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
- `intelligence_findings`
- `polymarket_intel`

Contract policy:
- treat the selected primary Polymarket contract as the canonical resolution anchor
- derive the operative date/deadline from the contract question and resolution description, not just the API close timestamp and not just the user's shorthand
- if the user's wording says one date but the selected contract resolves on another, do not silently proceed with the mismatch
- either update the tracked topic so the topic/query matches the selected contract, or tell the operator the contract/date mismatch explicitly
- never "fix" junk actors by hardcoding ad-hoc banned names; filtering must stay dynamic and anchored to the contract question, description, and topic terms

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

This is expected to produce a seed-only run. Do not describe a seed-only run as a failed simulation or as an LLM auth problem unless a fresh `health` check or a direct runtime error proves that.

Seed packet plus MiroFish simulation:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  run-tracked iran-conflict \
  --simulate
```

If the operator wants to edit or prune the cast before the next run, export a profile manifest from a finished simulation first:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  profile-template \
  --simulation-id sim_0e4e0705893c
```

Then wire that JSON back into the tracked topic:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  update-topic iran-conflict \
  --set-profile-overrides-path /absolute/path/to/profile-manifest.json
```

The manifest is operator-editable. Use it to disable weak actors or rewrite `entity_type`, `name`, `user_name`, `persona`, `bio`, and related profile fields before the next run.

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
- `--set-topic <text>` and `--set-market-query <text>`: realign the tracked topic to the actual contract being targeted
- `--set-keyword <term>`, `--add-keyword <term>`, `--remove-keyword <term>`
- `--add-region-code <code>`, `--remove-region-code <code>`
- `--set-module-param 'module.key=value'`
- `--remove-module-param module.key` or `--remove-module-param module`
- `--set-platform twitter|reddit|parallel`
- `--set-max-rounds <n>`
- `--set-profile-overrides-path /absolute/path/to/profile-manifest.json`

Natural Hermes ask patterns for module control:
- "Use PrediHermes list-worldosint-modules and propose the best modules for Hormuz risk."
- "Use PrediHermes update-topic iran-conflict and add <module>, remove <module>, then show dashboard."

## How to use the output

After a run:
- read `run_summary.md`
- if simulation ran, read `simulation_summary.md`
- use the selected primary contract question and description as the resolution anchor
- prefer the contract's own resolution date wording over loose topic labels or stale API close timestamps
- if the selected contract date conflicts with the topic label, say that plainly and normalize the topic before treating future runs as comparable
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
- curated intelligence findings and matched Polymarket flow
- simulation status/action totals when simulation artifacts exist
- decision call, confidence, and top alerts from the compiled artifact layer

PrediHermes also exposes a Rust local workbench so operators can browse topics, runs, evidence, alerts, accountability, and branch summaries without the web frontend:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  tui \
  --topic-id iran-conflict
```

The `tui` command will compile the latest artifacts first, then launch the local workbench.
It now includes:
- a large ASCII `PREDIHERMES` boot header
- a short loading sequence before the control room comes online
- dedicated panes for Topics, Runs, Branches, and Details
- lightweight live motion in the header and signal bars so focus and status stay visible in the terminal

Useful TUI controls:
- `1` / `2` / `3` / `4` / `5`: jump focus to Topics, Runs, Branches, Tabs, or Detail
- `Tab`: cycle focus across panes
- `j` / `k`: move inside the active pane
- `h` / `l`: change detail tab
- `Enter`: from Branches, open the selected branch detail directly
- `c`: print a ready-to-run `create-branch` command template into the footer based on the selected run
- `?`: toggle the help overlay
- `r`: reload compiled artifacts
- `q`: quit

If the user wants a non-interactive refresh without opening the workbench:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  compile-artifacts \
  --topic-id iran-conflict
```

To show command awareness/help for users inside Hermes:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py command-catalog
```

If the operator wants to create a new counterfactual branch without touching the web UI, use:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  create-branch \
  --base-simulation-id sim_19463d1a091e \
  --actor-name "Swiss backchannel envoy" \
  --entity-type Diplomat \
  --profession Diplomat \
  --country Switzerland \
  --persona "Quiet mediator pushing phased verification and face-saving sequencing." \
  --bio "Backchannel envoy with access to both US and Iranian negotiators." \
  --interested-topic Diplomacy \
  --interested-topic Verification \
  --injection-round 8 \
  --opening-statement "Swiss channel indicates a verification-first formula could still bridge the deadline gap."
```

Use `--start` if the user wants the branch launched immediately after creation. Use `--wait` only when they explicitly want the command to block for branch startup confirmation.

When responding in Hermes, if a user asks “what can PrediHermes do next?”, use `command-catalog` and then suggest 1-2 relevant next commands.

Do not invent exact resolution criteria if the market description is vague. Say when the market page needs manual verification.

## Local model path

PrediHermes stays local-first, but the MiroFish simulation backend uses whatever OpenAI-compatible model endpoint the backend is configured to call through:
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `LLM_API_KEY`

That means the operator can keep the full loop local by pointing MiroFish at a local OpenAI-compatible runtime such as Ollama, LM Studio, or vLLM. If the environment still points to a cloud endpoint, say that explicitly instead of implying the run stayed local.

Current repo default:
- `LLM_BASE_URL=http://127.0.0.1:11434/v1`
- `LLM_MODEL_NAME=qwen2.5:7b`
- `LLM_API_KEY=ollama`
- `LOCAL_GRAPH_EXTRACTION_MODE=fast`
- `LOCAL_SIMULATION_PROFILE=lean`
- `LOCAL_SIM_MAX_AGENTS=48`
- `LOCAL_SIM_MAX_ROUNDS=16`
- `LOCAL_LLM_REQUEST_TIMEOUT_SECONDS=900`
- `LOCAL_LLM_MAX_TOKENS=192`

If `GRAPH_BACKEND=local`, PrediHermes should stay on the local graph path even when a legacy `ZEP_API_KEY` is still present in the env. Do not blame Zep quota in that case unless a direct runtime error proves the backend is still hitting Zep.

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

If the user wants to test how a new actor would change a past simulation, use the PrediHermes helper first. Do not require the UI.

Prerequisites:
- MiroFish backend must be running on `MIROFISH_BASE_URL` and should expose `POST /api/simulation/<base_simulation_id>/counterfactual`
- the base simulation must already exist

Workflow:
1. choose the historical `simulation_id`
2. create a counterfactual branch with `create-branch`
3. read the returned branch `simulation_id`
4. if needed, start the new branch with `--start` or the normal `/api/simulation/start` call
5. poll `run-status`, `run-status/detail`, `timeline`, and `actions` like any other simulation

Recommended use:
- inject one actor at a time
- choose the injection round from a historically important or high-action round
- provide an `opening_statement` only if the user explicitly wants the actor to announce itself at insertion time

Preferred branch creation path:

```bash
python3 ~/.hermes/skills/research/geopolitical-market-sim/scripts/geopolitical_market_pipeline.py \
  create-branch \
  --base-simulation-id <base_simulation_id> \
  --actor-name "Swiss backchannel envoy" \
  --entity-type Diplomat \
  --profession Diplomat \
  --country Switzerland \
  --stance mediator \
  --bio "Quiet envoy coordinating verification-first diplomacy." \
  --persona "Prioritizes de-escalation, inspection sequencing, and face-saving language for both sides." \
  --interested-topic "backchannel diplomacy" \
  --interested-topic "IAEA inspections" \
  --interested-topic "sanctions relief" \
  --injection-round 12 \
  --opening-statement "Swiss channel update: verification-first sequencing is the only viable path."
```

Direct API fallback if the helper is unavailable:

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
