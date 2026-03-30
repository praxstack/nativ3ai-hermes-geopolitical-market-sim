from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

OFFICIAL_SOURCES = {
    "state department",
    "defense department",
    "usni news",
    "state.gov",
    "defense.gov",
    "iaea",
    "white house",
}

THEME_WEIGHTS = {
    "Diplomacy and nuclear file": 1.8,
    "Regime stability": -0.8,
    "Cyber and information control": -0.4,
    "Shipping and energy": -1.2,
    "Kinetic conflict": -1.6,
    "General conflict": -0.6,
}

ACTION_THEME_PATTERNS = {
    "Diplomacy and nuclear file": re.compile(r"deal|talks|ceasefire|diplomacy|inspection|verification|mediat|iaea|enrichment", re.I),
    "Shipping and energy": re.compile(r"hormuz|shipping|transit|premium|escort|fleet|oil|gulf", re.I),
    "Kinetic conflict": re.compile(r"strike|missile|drone|attack|offensive|war|retaliat", re.I),
    "Regime stability": re.compile(r"protest|succession|leader|regime|cabinet|coalition", re.I),
    "Cyber and information control": re.compile(r"cyber|blackout|network|internet|signal", re.I),
}

ROOT_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def to_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def short_dt(value: Any) -> str:
    dt = to_dt(value)
    if not dt:
        return "n/a"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def short_text(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def pct(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def midpoint(market: Dict[str, Any]) -> float:
    bid = market.get("bestBid")
    ask = market.get("bestAsk")
    if bid is not None and ask is not None:
        try:
            return (float(bid) + float(ask)) / 2.0
        except (TypeError, ValueError):
            pass
    prices = market.get("outcomePrices") or []
    if prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            pass
    return pct(market.get("lastTradePrice"))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def resolve_data_root(data_root: Optional[Path]) -> Path:
    if data_root:
        return data_root.expanduser()
    hermes_home = Path.home() / ".hermes"
    return hermes_home / "data" / "geopolitical-market-sim"


def resolve_mirofish_root(path: Optional[Path]) -> Path:
    if path:
        return path.expanduser()
    return Path.cwd()


def run_sort_key(run_dir: Path) -> str:
    return run_dir.name


def iter_run_dirs(data_root: Path, topic_id: str = "") -> Iterable[Path]:
    runs_root = data_root / "runs"
    if not runs_root.exists():
        return []
    if topic_id:
        topic_dirs = [runs_root / topic_id]
    else:
        topic_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    found: List[Path] = []
    for topic_dir in topic_dirs:
        if not topic_dir.exists():
            continue
        for run_dir in topic_dir.iterdir():
            if run_dir.is_dir():
                found.append(run_dir)
    return sorted(found, key=run_sort_key)


def parse_markdown_value(markdown_text: str, label: str) -> str:
    prefix = f"- {label}:"
    for line in markdown_text.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip("`")
    return ""


def load_run_summary(run_dir: Path) -> str:
    path = run_dir / "run_summary.md"
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def load_mirofish_link(run_dir: Path) -> Dict[str, Any]:
    return load_json(run_dir / "mirofish_link.json")


def write_mirofish_link(run_dir: Path, payload: Dict[str, Any]) -> None:
    path = run_dir / "mirofish_link.json"
    existing = load_mirofish_link(run_dir)
    merged = {**existing, **payload}
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def simulation_candidate_time(sim_dir: Path, run_state: Dict[str, Any]) -> Optional[datetime]:
    for name in ("simulation_config.json", "state.json", "run_state.json"):
        path = sim_dir / name
        if not path.exists():
            continue
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
    started = to_dt(run_state.get("started_at"))
    if started:
        return started.astimezone(timezone.utc)
    return None


def infer_simulation_id(run_dir: Path, snapshot: Dict[str, Any], mirofish_root: Path) -> str:
    sims_root = mirofish_root / "backend" / "uploads" / "simulations"
    if not sims_root.exists():
        return ""
    generated_at = to_dt(snapshot.get("generated_at"))
    topic = str(snapshot.get("topic") or "")
    primary_market = ((snapshot.get("markets") or [{}])[0]) if isinstance(snapshot.get("markets"), list) else {}
    question = str(primary_market.get("question") or "")
    candidates: List[Tuple[int, float, str]] = []
    for sim_dir in sims_root.iterdir():
        if not sim_dir.is_dir():
            continue
        cfg = load_json(sim_dir / "simulation_config.json")
        run_state = load_json(sim_dir / "run_state.json")
        requirement = str(cfg.get("simulation_requirement") or "")
        if not requirement:
            continue
        requirement_lower = requirement.lower()
        score = 0
        if question and question.lower() in requirement_lower:
            score += 100
        if topic and topic.lower() in requirement_lower:
            score += 40
        if score == 0:
            continue
        candidate_time = simulation_candidate_time(sim_dir, run_state)
        delta_seconds = 9_999_999.0
        if generated_at and candidate_time:
            delta_seconds = abs((candidate_time - generated_at.astimezone(timezone.utc)).total_seconds())
            if delta_seconds > 4 * 3600:
                continue
        candidates.append((score, delta_seconds, sim_dir.name))
    if not candidates:
        return ""
    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
    return candidates[0][2]


def parse_action_texts(payload: Dict[str, Any]) -> Iterable[str]:
    for key, value in payload.items():
        if not isinstance(value, str):
            continue
        key_lower = key.lower()
        if any(token in key_lower for token in ("content", "statement", "text", "message")):
            yield value


def classify_text_theme(text: str) -> str:
    for theme, pattern in ACTION_THEME_PATTERNS.items():
        if pattern.search(text or ""):
            return theme
    return "General conflict"


def parse_action_log(path: Path) -> Dict[str, Any]:
    event_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    agents: Counter[str] = Counter()
    theme_counts: Counter[str] = Counter()
    round_activity: Counter[int] = Counter()
    evidence: List[Dict[str, Any]] = []
    lines = 0
    if not path.exists():
        return {
            "lines": 0,
            "event_counts": {},
            "action_counts": {},
            "top_agents": [],
            "theme_counts": {},
            "evidence": [],
        }
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            lines += 1
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event_type = payload.get("event_type", "unknown")
            event_counts[event_type] += 1
            action_type = payload.get("action_type") or "UNKNOWN"
            if action_type != "UNKNOWN":
                action_counts[action_type] += 1
                agent_name = str(payload.get("agent_name") or "unknown")
                agents[agent_name] += 1
                round_value = payload.get("round")
                if isinstance(round_value, int):
                    round_activity[round_value] += 1
            for text in parse_action_texts(payload.get("action_args") or {}):
                theme = classify_text_theme(text)
                theme_counts[theme] += 1
                if len(evidence) < 18:
                    evidence.append(
                        {
                            "text": short_text(text, 220),
                            "theme": theme,
                            "agent": agent_name,
                            "timestamp": payload.get("timestamp"),
                            "action": action_type,
                            "platform": payload.get("platform"),
                        }
                    )
    return {
        "lines": lines,
        "event_counts": dict(event_counts),
        "action_counts": dict(action_counts.most_common()),
        "agent_counts": dict(agents.most_common()),
        "top_agents": agents.most_common(8),
        "theme_counts": dict(theme_counts.most_common()),
        "round_activity": dict(sorted(round_activity.items())),
        "evidence": evidence,
    }


@dataclass
class Driver:
    label: str
    polarity: str
    strength: float
    explanation: str
    evidence_ids: List[str]


@dataclass
class Alert:
    kind: str
    level: str
    message: str
    delta: Optional[float] = None


@dataclass
class ArtifactPaths:
    decision: str
    evidence: str
    alerts: str
    branch: Optional[str] = None


@dataclass
class RunSummary:
    topic_id: str
    topic: str
    run_id: str
    generated_at: str
    market_question: str
    market_yes_probability: float
    predicted_yes_probability: float
    call: str
    confidence: float
    dominant_theme: str
    simulation_status: str
    artifact_paths: ArtifactPaths


def build_market_section(primary_market: Dict[str, Any]) -> Dict[str, Any]:
    market_mid = midpoint(primary_market)
    resolution_deadline = primary_market.get("resolutionDeadline") or short_dt(primary_market.get("endDate"))
    return {
        "question": primary_market.get("question") or "n/a",
        "description": primary_market.get("description") or "",
        "url": primary_market.get("url") or "",
        "deadline": primary_market.get("endDate"),
        "deadline_display": resolution_deadline,
        "market_close_display": short_dt(primary_market.get("endDate")),
        "best_bid": pct(primary_market.get("bestBid")),
        "best_ask": pct(primary_market.get("bestAsk")),
        "yes_probability": market_mid,
        "spread": pct(primary_market.get("spread")),
        "volume": float(primary_market.get("volumeNum") or 0),
        "liquidity": float(primary_market.get("liquidityNum") or 0),
        "resolution_notes": short_text(primary_market.get("description"), 700),
    }


def ordered_round_series(*round_maps: Dict[str, Any]) -> List[int]:
    counters: List[Counter[int]] = []
    max_round = 0
    for mapping in round_maps:
        counter: Counter[int] = Counter()
        for key, value in (mapping or {}).items():
            try:
                round_id = int(key)
                count = int(value or 0)
            except (TypeError, ValueError):
                continue
            counter[round_id] += count
            max_round = max(max_round, round_id)
        counters.append(counter)
    if max_round <= 0:
        return []
    combined = Counter()
    for counter in counters:
        combined.update(counter)
    return [int(combined.get(round_id, 0)) for round_id in range(1, max_round + 1)]


def build_evidence(snapshot: Dict[str, Any], simulation: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    news = snapshot.get("news") or {}
    for index, item in enumerate((news.get("items") or [])[:14], start=1):
        source = str(item.get("source") or "unknown")
        evidence.append(
            {
                "id": f"news-{index}",
                "kind": "headline",
                "title": item.get("title") or "",
                "source": source,
                "url": item.get("link") or "",
                "timestamp": item.get("pubDateIso") or item.get("pubDate") or "",
                "theme": classify_text_theme(item.get("title") or ""),
                "credibility": "official" if source.lower() in OFFICIAL_SOURCES else "media",
                "impact": "market-moving" if source.lower() in OFFICIAL_SOURCES else "supporting",
            }
        )
    for index, row in enumerate((snapshot.get("context") or {}).get("riskRows") or [], start=1):
        evidence.append(
            {
                "id": f"risk-{index}",
                "kind": "risk_score",
                "title": f"{row.get('region', 'n/a')} combined risk {row.get('combinedScore', 'n/a')}",
                "source": "WorldOSINT intelligence_risk_scores",
                "url": "",
                "timestamp": snapshot.get("generated_at") or "",
                "theme": "Kinetic conflict",
                "credibility": "sensor",
                "impact": "supporting",
            }
        )
    for index, row in enumerate((snapshot.get("context") or {}).get("theaterAssets") or [], start=1):
        evidence.append(
            {
                "id": f"asset-{index}",
                "kind": "posture",
                "title": f"{row.get('name') or 'Asset'} in {row.get('region') or 'unknown region'} ({row.get('status') or 'status n/a'})",
                "source": "WorldOSINT military_usni",
                "url": row.get("articleUrl") or "",
                "timestamp": snapshot.get("generated_at") or "",
                "theme": "Shipping and energy",
                "credibility": "sensor",
                "impact": "supporting",
            }
        )
    for index, row in enumerate((simulation.get("evidence") or [])[:8], start=1):
        evidence.append(
            {
                "id": f"sim-{index}",
                "kind": "simulation",
                "title": row.get("text") or "",
                "source": row.get("agent") or "simulation",
                "url": "",
                "timestamp": row.get("timestamp") or "",
                "theme": row.get("theme") or "General conflict",
                "credibility": "simulation",
                "impact": "supporting",
            }
        )
    intelligence_findings = ((((snapshot.get("extra_modules") or {}).get("intelligence_findings") or {}).get("data") or {}).get("findings") or [])
    for index, row in enumerate(intelligence_findings[:8], start=1):
        evidence.append(
            {
                "id": f"finding-{index}",
                "kind": str(row.get("type") or "finding"),
                "title": row.get("title") or "",
                "source": row.get("source") or "intelligence_findings",
                "url": "",
                "timestamp": row.get("timestamp") or "",
                "theme": classify_text_theme(" ".join([str(row.get("title") or ""), str(row.get("summary") or "")])),
                "credibility": "signal",
                "impact": str(row.get("priority") or "supporting"),
            }
        )
    matched_trades = ((((snapshot.get("extra_modules") or {}).get("polymarket_intel") or {}).get("data") or {}).get("matched_trades") or [])
    for index, row in enumerate(matched_trades[:6], start=1):
        evidence.append(
            {
                "id": f"flow-{index}",
                "kind": "market_flow",
                "title": f"{row.get('side') or 'trade'} {row.get('outcome') or ''} notional {row.get('tradeNotional') or 0}",
                "source": "polymarket_intel",
                "url": "",
                "timestamp": row.get("timestamp") or "",
                "theme": "General conflict",
                "credibility": "market",
                "impact": "supporting",
            }
        )
    crypto_quotes = ((((snapshot.get("extra_modules") or {}).get("markets_crypto") or {}).get("data") or {}).get("quotes") or [])
    for index, row in enumerate(crypto_quotes[:4], start=1):
        evidence.append(
            {
                "id": f"crypto-{index}",
                "kind": "market_quote",
                "title": f"{row.get('name') or row.get('symbol')}: {row.get('price')} ({row.get('change')}%)",
                "source": "markets_crypto",
                "url": "",
                "timestamp": snapshot.get("generated_at") or "",
                "theme": "General conflict",
                "credibility": "market",
                "impact": "supporting",
            }
        )
    return evidence


def derive_signal_scores(snapshot: Dict[str, Any], simulation: Dict[str, Any]) -> Dict[str, float]:
    theme_counts = Counter()
    for row in (snapshot.get("news") or {}).get("themes") or []:
        theme_counts[str(row.get("theme") or "General conflict")] += int(row.get("count") or 0)
    sim_theme_counts = Counter(simulation.get("theme_counts") or {})
    official_count = 0
    for item in (snapshot.get("news") or {}).get("items") or []:
        source = str(item.get("source") or "").strip().lower()
        if source in OFFICIAL_SOURCES:
            official_count += 1
    risk_rows = (snapshot.get("context") or {}).get("riskRows") or []
    risk_values: List[float] = []
    for row in risk_rows:
        try:
            risk_values.append(float(row.get("combinedScore") or 0))
        except (TypeError, ValueError):
            continue
    risk_avg = sum(risk_values) / len(risk_values) if risk_values else 0.0
    findings_summary = ((((snapshot.get("extra_modules") or {}).get("intelligence_findings") or {}).get("data") or {}).get("summary") or {})
    critical_findings = float(findings_summary.get("critical") or 0)
    high_findings = float(findings_summary.get("high") or 0)
    finding_pressure = critical_findings * 0.8 + high_findings * 0.4
    diplomacy = theme_counts["Diplomacy and nuclear file"] + 0.4 * sim_theme_counts["Diplomacy and nuclear file"]
    conflict = (
        theme_counts["Kinetic conflict"]
        + theme_counts["Shipping and energy"] * 0.8
        + theme_counts["General conflict"] * 0.5
        + 0.4 * sim_theme_counts["Kinetic conflict"]
        + 0.2 * sim_theme_counts["Shipping and energy"]
        + risk_avg / 4.5
        + finding_pressure
    )
    return {
        "official_count": float(official_count),
        "risk_average": risk_avg,
        "diplomacy_pressure": diplomacy,
        "conflict_pressure": conflict,
        "finding_pressure": finding_pressure,
        "finding_count": float(findings_summary.get("total") or 0),
    }


def derive_probabilities(snapshot: Dict[str, Any], simulation: Dict[str, Any], market_section: Dict[str, Any]) -> Dict[str, float]:
    scores = derive_signal_scores(snapshot, simulation)
    market_yes = market_section["yes_probability"]
    headline_count = len((snapshot.get("news") or {}).get("items") or [])
    delta = (
        scores["diplomacy_pressure"] * 0.012
        + scores["official_count"] * 0.01
        - scores["conflict_pressure"] * 0.01
    )
    adjusted_yes = clamp(market_yes + delta, 0.01, 0.99)
    confidence = clamp(
        0.45 + abs(adjusted_yes - market_yes) * 2.4 + min(headline_count / 200.0, 0.18),
        0.05,
        0.96,
    )
    return {
        "market_yes_probability": round(market_yes, 4),
        "predicted_yes_probability": round(adjusted_yes, 4),
        "edge": round(adjusted_yes - market_yes, 4),
        "confidence": round(confidence, 4),
    }


def choose_call(predicted_yes: float) -> str:
    return "YES" if predicted_yes >= 0.5 else "NO"


def select_evidence_ids(evidence: List[Dict[str, Any]], *, theme: str = "", kind: str = "") -> List[str]:
    output: List[str] = []
    for row in evidence:
        if theme and row.get("theme") != theme:
            continue
        if kind and row.get("kind") != kind:
            continue
        output.append(str(row.get("id")))
        if len(output) >= 3:
            break
    return output


def build_drivers(snapshot: Dict[str, Any], simulation: Dict[str, Any], market_section: Dict[str, Any], evidence: List[Dict[str, Any]], probs: Dict[str, float]) -> List[Driver]:
    scores = derive_signal_scores(snapshot, simulation)
    drivers: List[Driver] = []
    if scores["conflict_pressure"] >= scores["diplomacy_pressure"]:
        drivers.append(
            Driver(
                label="Escalation pressure dominates negotiation pressure",
                polarity="bearish-yes",
                strength=round(scores["conflict_pressure"], 2),
                explanation="Conflict, shipping, and posture signals outweigh diplomacy evidence in the current packet.",
                evidence_ids=select_evidence_ids(evidence, theme="Kinetic conflict") + select_evidence_ids(evidence, theme="Shipping and energy"),
            )
        )
    else:
        drivers.append(
            Driver(
                label="Diplomatic signals are concentrated enough to keep a Yes path alive",
                polarity="bullish-yes",
                strength=round(scores["diplomacy_pressure"], 2),
                explanation="Negotiation and verification language appears often enough to lift the contract above raw market pricing.",
                evidence_ids=select_evidence_ids(evidence, theme="Diplomacy and nuclear file"),
            )
        )
    drivers.append(
        Driver(
            label="Market pricing vs internal forecast gap",
            polarity="bullish-yes" if probs["edge"] > 0 else "bearish-yes",
            strength=round(abs(probs["edge"]) * 100, 2),
            explanation=f"Compiled view prices Yes at {probs['predicted_yes_probability']:.1%} versus market midpoint {probs['market_yes_probability']:.1%}.",
            evidence_ids=select_evidence_ids(evidence, kind="headline")[:2],
        )
    )
    drivers.append(
        Driver(
            label="Official-source confirmation threshold",
            polarity="bullish-yes" if scores["official_count"] else "bearish-yes",
            strength=round(scores["official_count"], 2),
            explanation="Official statements remain the cleanest path to market resolution, so official-source density materially matters.",
            evidence_ids=select_evidence_ids(evidence, kind="headline")[:2],
        )
    )
    if scores["finding_count"] > 0:
        drivers.append(
            Driver(
                label="Filtered intelligence findings raised short-horizon risk pressure",
                polarity="bearish-yes",
                strength=round(scores["finding_pressure"], 2),
                explanation="Curated intelligence findings contributed additional conflict pressure after topic filtering, so the call is not relying on RSS headlines alone.",
                evidence_ids=select_evidence_ids(evidence, kind="cyber_threat")
                + select_evidence_ids(evidence, kind="seismic")
                + select_evidence_ids(evidence, kind="finding"),
            )
        )
    if simulation.get("lines"):
        drivers.append(
            Driver(
                label="Simulation activity pressure",
                polarity="context",
                strength=round(float(simulation.get("lines") or 0), 2),
                explanation="High action volume indicates the simulated information environment is active enough to stress-test the thesis rather than rely only on raw headlines.",
                evidence_ids=select_evidence_ids(evidence, kind="simulation"),
            )
        )
    return drivers[:4]


def build_invalidation(call: str) -> List[str]:
    if call == "NO":
        return [
            "A public US-Iran announcement establishes a verification-first agreement before the market deadline.",
            "Credible multilateral reporting converges on an agreed framework with both Washington and Tehran confirmed as parties.",
            "IAEA or mediator activity moves from exploratory chatter to named timetable and sign-off language.",
        ]
    return [
        "Regional kinetic escalation or Gulf transit disruption displaces the negotiating window.",
        "Officials on either side publicly reject the deal path or harden sequencing demands near the deadline.",
        "Verification milestones slip without an announced framework before the market deadline.",
    ]


def build_summary(snapshot: Dict[str, Any], simulation: Dict[str, Any], market_section: Dict[str, Any], probs: Dict[str, float], drivers: List[Driver], call: str) -> Dict[str, str]:
    dominant_theme = ((snapshot.get("news") or {}).get("themes") or [{"theme": "General conflict"}])[0]["theme"]
    if dominant_theme == "General conflict" and simulation.get("theme_counts"):
        dominant_theme = next(iter(simulation.get("theme_counts") or {}), "General conflict")
    action_total = int(simulation.get("total_actions") or simulation.get("lines") or 0)
    thesis = (
        f"PrediHermes calls {call} on '{market_section['question']}' with {probs['confidence']:.0%} confidence. "
        f"The compiled view prices Yes at {probs['predicted_yes_probability']:.1%} against a market midpoint of {probs['market_yes_probability']:.1%}."
    )
    why_now = (
        f"Headline dominance currently sits in '{dominant_theme}', while simulation activity totals {action_total} logged actions. "
        f"The strongest driver is '{drivers[0].label.lower()}'."
    )
    return {
        "thesis": thesis,
        "why_now": why_now,
        "operator_note": "Use the evidence panel to verify whether the market is underreacting to diplomacy milestones or correctly discounting them.",
    }


def build_branch_summary(simulation_id: str, mirofish_root: Path) -> Optional[Dict[str, Any]]:
    sim_dir = mirofish_root / "backend" / "uploads" / "simulations" / simulation_id
    cfg = load_json(sim_dir / "simulation_config.json")
    counterfactual = cfg.get("counterfactual") if isinstance(cfg.get("counterfactual"), dict) else {}
    if not counterfactual:
        return None
    base_id = str(counterfactual.get("base_simulation_id") or "")
    base_dir = mirofish_root / "backend" / "uploads" / "simulations" / base_id
    branch_state = load_json(sim_dir / "run_state.json")
    base_state = load_json(base_dir / "run_state.json")
    branch_twitter = parse_action_log(sim_dir / "twitter" / "actions.jsonl")
    base_twitter = parse_action_log(base_dir / "twitter" / "actions.jsonl")
    action_delta = int(branch_state.get("total_actions_count") or branch_twitter.get("lines") or 0) - int(base_state.get("total_actions_count") or base_twitter.get("lines") or 0)
    diplomacy_delta = int((branch_twitter.get("theme_counts") or {}).get("Diplomacy and nuclear file", 0)) - int((base_twitter.get("theme_counts") or {}).get("Diplomacy and nuclear file", 0))
    conflict_delta = int((branch_twitter.get("theme_counts") or {}).get("Kinetic conflict", 0)) - int((base_twitter.get("theme_counts") or {}).get("Kinetic conflict", 0))
    interpretation = "materially altered" if abs(action_delta) > 25 or abs(diplomacy_delta - conflict_delta) > 10 else "close to base"
    return {
        "enabled": True,
        "simulation_id": simulation_id,
        "base_simulation_id": base_id,
        "actor_name": counterfactual.get("actor_name"),
        "entity_type": counterfactual.get("entity_type"),
        "injection_round": counterfactual.get("injection_round"),
        "opening_statement": counterfactual.get("opening_statement"),
        "action_delta": action_delta,
        "diplomacy_delta": diplomacy_delta,
        "conflict_delta": conflict_delta,
        "interpretation": interpretation,
    }


def build_alerts(current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> List[Alert]:
    alerts: List[Alert] = []
    if not previous:
        alerts.append(Alert(kind="bootstrap", level="info", message="First compiled run for this topic; no prior baseline yet."))
        return alerts
    current_market = current["market"]["yes_probability"]
    previous_market = previous["market"]["yes_probability"]
    market_delta = round(current_market - previous_market, 4)
    if abs(market_delta) >= 0.02:
        alerts.append(Alert(kind="market_move", level="warning", delta=market_delta, message=f"Market midpoint moved {market_delta:+.1%} versus the previous run."))
    current_pred = current["forecast"]["predicted_yes_probability"]
    previous_pred = previous["forecast"]["predicted_yes_probability"]
    pred_delta = round(current_pred - previous_pred, 4)
    if current["forecast"]["call"] != previous["forecast"]["call"]:
        alerts.append(Alert(kind="call_flip", level="critical", delta=pred_delta, message=f"PrediHermes call flipped from {previous['forecast']['call']} to {current['forecast']['call']}."))
    elif abs(pred_delta) >= 0.08:
        alerts.append(Alert(kind="thesis_drift", level="warning", delta=pred_delta, message=f"Predicted Yes probability shifted {pred_delta:+.1%} versus the previous run."))
    cur_theme = current["signals"].get("dominant_theme")
    prev_theme = previous["signals"].get("dominant_theme")
    if cur_theme != prev_theme:
        alerts.append(Alert(kind="theme_shift", level="info", message=f"Dominant theme changed from '{prev_theme}' to '{cur_theme}'."))
    cur_risk = current["signals"].get("risk_average") or 0.0
    prev_risk = previous["signals"].get("risk_average") or 0.0
    risk_delta = round(cur_risk - prev_risk, 2)
    if abs(risk_delta) >= 3:
        alerts.append(Alert(kind="risk_shift", level="warning", delta=risk_delta, message=f"Average risk score moved {risk_delta:+.2f} points."))
    if not alerts:
        alerts.append(Alert(kind="steady", level="info", message="No material drift versus the previous compiled run."))
    return alerts


def compile_run_artifact(run_dir: Path, mirofish_root: Path) -> Dict[str, Any]:
    snapshot_files = sorted(run_dir.glob("*_snapshot.json"))
    if not snapshot_files:
        raise FileNotFoundError(f"No snapshot file found in {run_dir}")
    snapshot = load_json(snapshot_files[-1])
    summary_markdown = load_run_summary(run_dir)
    has_summary = bool(summary_markdown.strip())
    link_payload = load_mirofish_link(run_dir)
    link_status = str(link_payload.get("status") or "").strip().lower()
    topic_id = str(snapshot.get("topic_id") or run_dir.parent.name)
    topic = str(snapshot.get("topic") or topic_id)
    simulation_id = parse_markdown_value(summary_markdown, "Simulation ID")
    if not simulation_id and link_status != "recovered":
        simulation_id = str(link_payload.get("simulation_id") or "")
    if not simulation_id and has_summary:
        simulation_id = infer_simulation_id(run_dir, snapshot, mirofish_root)
        if simulation_id:
            write_mirofish_link(
                run_dir,
                {
                    "version": 1,
                    "recovered_at": utc_now_iso(),
                    "simulation_id": simulation_id,
                    "status": "recovered",
                },
            )
    simulation: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "status": "seed-only",
        "lines": 0,
        "total_actions": 0,
        "total_rounds": 0,
        "action_counts": {},
        "top_agents": [],
        "theme_counts": {},
        "evidence": [],
        "agent_count": 0,
        "twitter_actions": 0,
        "reddit_actions": 0,
        "selected_entities": [],
        "admission_summary": {
            "candidate_count": 0,
            "selected_count": 0,
            "anchored_count": 0,
            "rejected_count": 0,
            "avg_score": 0.0,
        },
    }
    branch_summary = None
    if simulation_id:
        sim_dir = mirofish_root / "backend" / "uploads" / "simulations" / simulation_id
        state = load_json(sim_dir / "state.json")
        run_state = load_json(sim_dir / "run_state.json")
        sim_config = load_json(sim_dir / "simulation_config.json")
        twitter = parse_action_log(sim_dir / "twitter" / "actions.jsonl")
        reddit = parse_action_log(sim_dir / "reddit" / "actions.jsonl")
        combined_agents = Counter(twitter.get("agent_counts") or {}) + Counter(reddit.get("agent_counts") or {})
        action_counts = Counter({f"twitter::{key}": value for key, value in (twitter.get("action_counts") or {}).items()})
        action_counts.update({f"reddit::{key}": value for key, value in (reddit.get("action_counts") or {}).items()})
        selection_rows = [row for row in (sim_config.get("entity_selection") or []) if isinstance(row, dict)]
        selected_entities = sorted(
            [row for row in selection_rows if row.get("kept")],
            key=lambda row: float(row.get("score") or 0),
            reverse=True,
        )
        selected_count = len(selected_entities)
        anchored_count = sum(1 for row in selected_entities if int(row.get("anchor_overlap") or 0) > 0)
        avg_score = (
            sum(float(row.get("score") or 0.0) for row in selected_entities) / selected_count
            if selected_count
            else 0.0
        )
        simulation = {
            "simulation_id": simulation_id,
            "status": str(run_state.get("runner_status") or state.get("status") or "unknown"),
            "current_round": int(run_state.get("current_round") or state.get("current_round") or 0),
            "total_rounds": int(run_state.get("total_rounds") or 0),
            "lines": int((twitter.get("lines") or 0) + (reddit.get("lines") or 0)),
            "total_actions": int(run_state.get("total_actions_count") or 0),
            "action_counts": dict(action_counts.most_common()),
            "top_agents": combined_agents.most_common(8),
            "theme_counts": dict(Counter(twitter.get("theme_counts") or {}) + Counter(reddit.get("theme_counts") or {})),
            "evidence": (twitter.get("evidence") or [])[:10] + (reddit.get("evidence") or [])[:8],
            "agent_count": len((sim_config.get("agent_configs") or [])),
            "twitter_actions": int(run_state.get("twitter_actions_count") or 0),
            "reddit_actions": int(run_state.get("reddit_actions_count") or 0),
            "twitter_round_activity": ordered_round_series(twitter.get("round_activity") or {}),
            "reddit_round_activity": ordered_round_series(reddit.get("round_activity") or {}),
            "combined_round_activity": ordered_round_series(
                twitter.get("round_activity") or {},
                reddit.get("round_activity") or {},
            ),
            "updated_at": run_state.get("updated_at") or state.get("updated_at"),
            "selected_entities": selected_entities[:12],
            "admission_summary": {
                "candidate_count": len(selection_rows),
                "selected_count": selected_count,
                "anchored_count": anchored_count,
                "rejected_count": max(len(selection_rows) - selected_count, 0),
                "avg_score": round(avg_score, 2),
            },
        }
        branch_summary = build_branch_summary(simulation_id, mirofish_root)
    primary_market = ((snapshot.get("markets") or [{}])[0])
    market = build_market_section(primary_market)
    evidence = build_evidence(snapshot, simulation)
    signal_scores = derive_signal_scores(snapshot, simulation)
    probs = derive_probabilities(snapshot, simulation, market)
    call = choose_call(probs["predicted_yes_probability"])
    drivers = build_drivers(snapshot, simulation, market, evidence, probs)
    dominant_theme = (((snapshot.get("news") or {}).get("themes") or [{"theme": "General conflict"}])[0]).get("theme")
    risk_rows = (snapshot.get("context") or {}).get("riskRows") or []
    risk_values = []
    for row in risk_rows:
        try:
            risk_values.append(float(row.get("combinedScore") or 0))
        except (TypeError, ValueError):
            continue
    signals = {
        "headline_count": len((snapshot.get("news") or {}).get("items") or []),
        "dominant_theme": dominant_theme,
        "top_themes": (snapshot.get("news") or {}).get("themes") or [],
        "risk_average": round(sum(risk_values) / len(risk_values), 2) if risk_values else 0.0,
        "actor_candidates": (snapshot.get("news") or {}).get("actors") or [],
        "module_set": snapshot.get("headless_modules") or [],
        "official_source_count": sum(1 for row in evidence if row.get("kind") == "headline" and row.get("credibility") == "official"),
        "finding_count": int(signal_scores.get("finding_count") or 0),
    }
    artifact = {
        "version": ROOT_VERSION,
        "compiled_at": utc_now_iso(),
        "run_id": run_dir.name,
        "topic_id": topic_id,
        "topic": topic,
        "generated_at": snapshot.get("generated_at") or "",
        "paths": {
            "run_dir": str(run_dir),
            "snapshot": str(snapshot_files[-1]),
            "summary": str(run_dir / "run_summary.md"),
        },
        "market": market,
        "signals": signals,
        "simulation": simulation,
        "forecast": {
            **probs,
            "call": call,
            "drivers": [asdict(driver) for driver in drivers],
            "invalidation": build_invalidation(call),
            **build_summary(snapshot, simulation, market, probs, drivers, call),
        },
        "branch": branch_summary,
    }
    evidence_payload = {
        "version": ROOT_VERSION,
        "compiled_at": artifact["compiled_at"],
        "run_id": artifact["run_id"],
        "topic_id": topic_id,
        "evidence": evidence,
    }
    decision_path = run_dir / "decision_artifact.json"
    evidence_path = run_dir / "evidence_lineage.json"
    branch_path = run_dir / "branch_summary.json"
    decision_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence_path.write_text(json.dumps(evidence_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if branch_summary:
        branch_path.write_text(json.dumps(branch_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    elif branch_path.exists():
        branch_path.unlink()
    return artifact


def compile_artifacts(*, data_root: Optional[Path] = None, mirofish_root: Optional[Path] = None, topic_id: str = "") -> Dict[str, Any]:
    data_root = resolve_data_root(data_root)
    mirofish_root = resolve_mirofish_root(mirofish_root)
    compiled_root = data_root / "compiled"
    compiled_root.mkdir(parents=True, exist_ok=True)
    accountability_root = compiled_root / "accountability"
    accountability_root.mkdir(parents=True, exist_ok=True)

    run_artifacts: List[Dict[str, Any]] = []
    for run_dir in iter_run_dirs(data_root, topic_id=topic_id):
        try:
            artifact = compile_run_artifact(run_dir, mirofish_root)
        except FileNotFoundError:
            continue
        run_artifacts.append(artifact)

    run_artifacts.sort(key=lambda row: (row.get("topic_id", ""), row.get("generated_at", ""), row.get("run_id", "")))

    previous_by_topic: Dict[str, Dict[str, Any]] = {}
    topic_ledgers: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    topic_summaries: List[Dict[str, Any]] = []
    branch_summaries: List[Dict[str, Any]] = []
    run_summaries: List[RunSummary] = []

    for artifact in run_artifacts:
        alerts = build_alerts(artifact, previous_by_topic.get(artifact["topic_id"]))
        alert_payload = {
            "version": ROOT_VERSION,
            "compiled_at": utc_now_iso(),
            "run_id": artifact["run_id"],
            "topic_id": artifact["topic_id"],
            "alerts": [asdict(alert) for alert in alerts],
        }
        run_dir = Path(artifact["paths"]["run_dir"])
        alerts_path = run_dir / "alerts.json"
        alerts_path.write_text(json.dumps(alert_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        branch_path = str(run_dir / "branch_summary.json") if artifact.get("branch") else None
        run_summaries.append(
            RunSummary(
                topic_id=artifact["topic_id"],
                topic=artifact["topic"],
                run_id=artifact["run_id"],
                generated_at=artifact.get("generated_at") or "",
                market_question=artifact["market"]["question"],
                market_yes_probability=artifact["forecast"]["market_yes_probability"],
                predicted_yes_probability=artifact["forecast"]["predicted_yes_probability"],
                call=artifact["forecast"]["call"],
                confidence=artifact["forecast"]["confidence"],
                dominant_theme=artifact["signals"]["dominant_theme"],
                simulation_status=artifact["simulation"]["status"],
                artifact_paths=ArtifactPaths(
                    decision=str(run_dir / "decision_artifact.json"),
                    evidence=str(run_dir / "evidence_lineage.json"),
                    alerts=str(alerts_path),
                    branch=branch_path,
                ),
            )
        )
        topic_ledgers[artifact["topic_id"]].append(
            {
                "run_id": artifact["run_id"],
                "generated_at": artifact.get("generated_at") or "",
                "call": artifact["forecast"]["call"],
                "confidence": artifact["forecast"]["confidence"],
                "market_yes_probability": artifact["forecast"]["market_yes_probability"],
                "predicted_yes_probability": artifact["forecast"]["predicted_yes_probability"],
                "edge": artifact["forecast"]["edge"],
                "dominant_theme": artifact["signals"]["dominant_theme"],
                "simulation_status": artifact["simulation"]["status"],
            }
        )
        previous_by_topic[artifact["topic_id"]] = artifact
        if artifact.get("branch"):
            branch_summaries.append(artifact["branch"])

    for topic, rows in topic_ledgers.items():
        rows.sort(key=lambda row: (row.get("generated_at", ""), row.get("run_id", "")))
        latest = rows[-1]
        ledger_payload = {
            "version": ROOT_VERSION,
            "compiled_at": utc_now_iso(),
            "topic_id": topic,
            "run_count": len(rows),
            "latest_call": latest["call"],
            "latest_confidence": latest["confidence"],
            "records": rows,
        }
        (accountability_root / f"{topic}.json").write_text(json.dumps(ledger_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        topic_summaries.append(
            {
                "topic_id": topic,
                "run_count": len(rows),
                "latest_run_id": latest["run_id"],
                "latest_call": latest["call"],
                "latest_confidence": latest["confidence"],
                "latest_market_yes_probability": latest["market_yes_probability"],
                "latest_predicted_yes_probability": latest["predicted_yes_probability"],
                "dominant_theme": latest["dominant_theme"],
                "accountability_path": str(accountability_root / f"{topic}.json"),
            }
        )

    index_payload = {
        "version": ROOT_VERSION,
        "compiled_at": utc_now_iso(),
        "data_root": str(data_root),
        "mirofish_root": str(mirofish_root),
        "topic_count": len(topic_summaries),
        "run_count": len(run_artifacts),
        "branch_count": len(branch_summaries),
        "topics": sorted(topic_summaries, key=lambda row: row["topic_id"]),
        "runs": [asdict(row) for row in run_summaries],
        "branches": sorted(branch_summaries, key=lambda row: (row.get("simulation_id") or "")),
    }
    index_path = compiled_root / "index.json"
    branches_path = compiled_root / "branches.json"
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    branches_path.write_text(json.dumps({"version": ROOT_VERSION, "compiled_at": utc_now_iso(), "branches": index_payload["branches"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_payload


def load_index(data_root: Optional[Path] = None) -> Dict[str, Any]:
    data_root = resolve_data_root(data_root)
    index_path = data_root / "compiled" / "index.json"
    return load_json(index_path)
