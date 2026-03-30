# PrediHermes

PrediHermes is the local-first operator layer that sits on top of WorldOSINT, Polymarket, and MiroFish.

It is built around one repeatable loop:
- ingest the topic packet
- select the live market anchor
- compile evidence lineage
- score the market against the packet
- compare branch or counterfactual runs
- emit one decision artifact

## Default feed lanes

The tracked-topic path now pulls a compact default feed set:
- `news_rss`
- `intelligence_risk_scores`
- `military_usni`
- `intelligence_findings`
- `polymarket_intel`

`intelligence_findings` and `polymarket_intel` are curated locally before they land in the snapshot so the operator view stays topic-scoped instead of dumping raw upstream noise into the evidence bus.

The simulation path now also writes a dedicated `simulation_brief.md` per run and feeds that into MiroFish graph construction instead of the full verbose seed packet. That keeps local graph extraction focused on concrete actors, states, outlets, and institutions instead of metadata labels or dashboard wording.

## Components

- `tmp_geopolitical_market_pipeline.py`
  - operator CLI
  - topic tracking
  - run orchestration
  - artifact compilation
  - ASCII dashboard
  - Rust TUI launcher
- `tools/predihermes/review.py`
  - artifact compiler
  - evidence lineage builder
  - decision artifact generator
  - alert and accountability ledger generation
  - counterfactual branch summaries
- `tools/predihermes_tui/`
  - Rust workbench for browsing compiled artifacts without the web frontend

## Core artifacts

Each run directory receives these compiled files:
- `decision_artifact.json`
- `evidence_lineage.json`
- `alerts.json`
- `branch_summary.json` when the run points at a counterfactual simulation

The shared compiled ledger lives under:
- `~/.hermes/data/geopolitical-market-sim/compiled/index.json`
- `~/.hermes/data/geopolitical-market-sim/compiled/accountability/<topic>.json`
- `~/.hermes/data/geopolitical-market-sim/compiled/branches.json`

## Fast path

The repo-local launcher `./predihermes` prefers `backend/.venv/bin/python` automatically, so use it for network-backed commands.

Compile the local ledgers:

```bash
./predihermes compile-artifacts \
  --mirofish-root /absolute/path/to/MiroFish-main
```

If you prefer the repo package surface, the root `package.json` also exposes:

```bash
npm run predihermes -- compile-artifacts --mirofish-root /absolute/path/to/MiroFish-main
```

Inspect the latest run in the terminal:

```bash
./predihermes dashboard \
  --topic-id iran-conflict \
  --mirofish-root /absolute/path/to/MiroFish-main
```

Open the Rust workbench:

```bash
./predihermes tui \
  --topic-id iran-conflict \
  --mirofish-root /absolute/path/to/MiroFish-main
```

Create a counterfactual branch from a finished base simulation:

```bash
./predihermes create-branch \
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

Export an operator-editable cast manifest from a finished simulation or graph:

```bash
./predihermes profile-template \
  --simulation-id sim_0e4e0705893c \
  --mirofish-root /absolute/path/to/MiroFish-main
```

Then attach that manifest to a tracked topic so the next run uses operator-authored profile overrides:

```bash
./predihermes update-topic iran-conflict \
  --set-profile-overrides-path /absolute/path/to/profile-manifest.json
```

The exported manifest is meant to be edited. You can disable entries or rewrite `entity_type`, `name`, `user_name`, `persona`, `bio`, and other profile fields before feeding it back into the next run.

Use `--debug-build` if you are iterating on the Rust workbench and do not want the release build path.

The workbench now behaves like a terminal control room:
- a large ASCII `PREDIHERMES` header on boot
- a short startup/loading sequence before the panes appear
- a dedicated Branches pane next to Topics and Runs
- a control-deck footer that exposes focus state, quick actions, and generated branch commands
- lightweight motion in the header, pane titles, and signal footer so active focus and live state are visible without adding a web frontend

## Rust workbench keys

- `1` / `2` / `3` / `4` / `5`: jump focus to Topics, Runs, Branches, Tabs, or Detail
- `Tab`: cycle focus between Topics, Runs, Branches, Tabs, and Detail
- `j` / `k`: move in the active pane
- `h` / `l`: change detail tab
- `Enter`: from the Branches pane, open the selected branch in the detail view
- `u` / `d`: scroll detail pane
- `c`: print a ready-to-run `create-branch` command template for the selected run
- `?`: toggle the help overlay
- `r`: reload compiled artifacts from disk
- `q`: quit

## Local model path

PrediHermes is local-first, but the simulation backend follows whatever model backend MiroFish is configured to use.

MiroFish already accepts any OpenAI-compatible endpoint through its existing environment variables:
- `LLM_BASE_URL`
- `LLM_MODEL_NAME`
- `LLM_API_KEY`

That means you can keep the full PrediHermes loop local by pointing MiroFish at a local OpenAI-compatible runtime such as Ollama, vLLM, or LM Studio.

Example pattern:

```env
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL_NAME=qwen2.5:7b
LLM_API_KEY=ollama
LOCAL_LLM_REQUEST_TIMEOUT_SECONDS=900
LOCAL_LLM_MAX_TOKENS=192
LOCAL_SIMULATION_PROFILE=lean
LOCAL_SIM_MAX_AGENTS=48
LOCAL_SIM_MAX_ROUNDS=16
```

PrediHermes itself does not hard-code a cloud provider. The current checkout will use whatever the MiroFish backend is configured to call.

For graph context, `GRAPH_BACKEND=local` now fully suppresses Zep enrichment in the simulation/profile path even if a stale `ZEP_API_KEY` is still present in `.env`. That keeps local mode actually local instead of leaking back into Zep quota errors.

For end-to-end local runs, the repo default also uses:
- `LOCAL_GRAPH_EXTRACTION_MODE=fast`
- `LOCAL_SIMULATION_PROFILE=lean`
- `LOCAL_SIM_MAX_AGENTS=48`
- `LOCAL_SIM_MAX_ROUNDS=16`

That combination keeps graph build, config generation, and simulation startup within a reasonable local loop on Ollama/Qwen instead of assuming cloud throughput. Switch the graph extraction mode to `llm` or relax the local sim caps only when you deliberately want a heavier run.

Profiles are deterministic by default in local mode. The local model should spend its budget on round-by-round replies and simulation behavior, not on re-randomizing the cast every run. Use the profile manifest when the operator wants to steer the cast manually.

## Operator model

PrediHermes is meant to answer six things quickly:
- what changed
- why it matters
- what market it affects
- what the current call is
- what would break the call
- how the branch differs from the base case

If a screen or artifact does not serve one of those questions, it should not be there.
