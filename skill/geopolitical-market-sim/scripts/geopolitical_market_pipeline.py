#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

try:
    import requests
    REQUEST_EXCEPTION = requests.RequestException
    HTTP_ERROR = requests.HTTPError
    REQUESTS_IMPORT_ERROR = None
except ImportError as exc:
    requests = None
    REQUESTS_IMPORT_ERROR = exc

    class REQUEST_EXCEPTION(Exception):
        pass

    class HTTP_ERROR(Exception):
        def __init__(self, *args: Any, response: Any = None):
            super().__init__(*args)
            self.response = response

USER_AGENT = "hermes-geopolitical-market-sim/0.1"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
DATA_DIR = HERMES_HOME / "data" / "geopolitical-market-sim"
STATE_PATH = DATA_DIR / "topics.json"
DEFAULT_WORLDOSINT_BASE = os.getenv("WORLDOSINT_BASE_URL", "http://127.0.0.1:3000")
DEFAULT_MIROFISH_BASE = os.getenv("MIROFISH_BASE_URL", "http://127.0.0.1:5001")
DEFAULT_MIROFISH_ROOT = Path(os.getenv("MIROFISH_ROOT", str(Path.home() / "MiroFish-main"))).expanduser()
DEFAULT_MAX_ROUNDS = 24
DEFAULT_PLATFORM = "parallel"
DEFAULT_DAYS = 7
DEFAULT_MAX_DEADLINE_DAYS = 31
DEFAULT_PARALLEL_PROFILE_COUNT = 6
DEFAULT_SIMULATION_MODE = "auto"
DEFAULT_BUDGET_USD = 1.0
DEFAULT_HEADLESS_MODULES = [
    "news_rss",
    "intelligence_risk_scores",
    "military_usni",
]
DEFAULT_CONSOLE_WIDTH = 92

THEATER_DEFAULTS = [
    "Persian Gulf",
    "Arabian Sea",
    "Red Sea",
    "Eastern Mediterranean Sea",
]

SOURCE_STOPWORDS = {
    "Reuters",
    "Associated Press",
    "AP",
    "Google News",
    "Al Jazeera",
    "USNI News",
    "State Department",
    "Defense Department",
    "Breaking",
    "Latest",
    "Update",
    "Analysis",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
}

CAPITALIZED_PHRASE_RE = re.compile(r"\b(?:[A-Z]{2,6}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")


class PipelineError(RuntimeError):
    pass


def require_requests() -> None:
    if requests is None:
        raise PipelineError(
            "The 'requests' package is required for network-backed commands. "
            "Install PrediHermes requirements or run this command from the Hermes venv."
        )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


def slugify(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "topic"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_state() -> Dict[str, Any]:
    ensure_dirs()
    if not STATE_PATH.exists():
        return {"version": 1, "topics": {}}
    with STATE_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {"version": 1, "topics": {}}
    data.setdefault("version", 1)
    data.setdefault("topics", {})
    return data


def looks_like_mirofish_root(path: Path) -> bool:
    return (path / "backend").is_dir() and (path / "frontend").is_dir()


def resolve_mirofish_root(value: Any) -> Path:
    requested = Path(str(value or DEFAULT_MIROFISH_ROOT)).expanduser()
    candidates: List[Path] = []
    for candidate in (
        requested,
        Path.cwd(),
        Path.home() / "Downloads" / requested.name,
        Path.home() / "Downloads" / "MiroFish-main",
        Path.home() / "MiroFish-main",
    ):
        candidate = candidate.expanduser()
        if candidate in candidates:
            continue
        candidates.append(candidate)
    for candidate in candidates:
        if looks_like_mirofish_root(candidate):
            return candidate
    return requested


def save_state(state: Dict[str, Any]) -> None:
    ensure_dirs()
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def to_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def short_dt(value: Any) -> str:
    dt = to_date(value)
    if not dt:
        return "n/a"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_json_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_json_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_scalar(value: str) -> Any:
    text = str(value).strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def dedupe_strings(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def normalize_headless_modules(value: Any) -> List[str]:
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    modules = dedupe_strings(items)
    return modules or list(DEFAULT_HEADLESS_MODULES)


def normalize_module_params(value: Any) -> Dict[str, Dict[str, Any]]:
    source = parse_json_mapping(value) if isinstance(value, str) else value
    if not isinstance(source, dict):
        return {}
    output: Dict[str, Dict[str, Any]] = {}
    for module_name, payload in source.items():
        name = str(module_name or "").strip()
        if not name:
            continue
        if isinstance(payload, dict):
            output[name] = payload
    return output


def parse_module_param_args(values: List[str]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for raw in values:
        text = str(raw or "").strip()
        if not text or "=" not in text:
            raise PipelineError(f"Invalid --module-param '{raw}'. Expected module.key=value or module={{...}}")
        left, right = text.split("=", 1)
        left = left.strip()
        if "." in left:
            module_name, key = left.split(".", 1)
            module_name = module_name.strip()
            key = key.strip()
            if not module_name or not key:
                raise PipelineError(f"Invalid --module-param '{raw}'. Expected module.key=value")
            output.setdefault(module_name, {})[key] = parse_scalar(right)
            continue
        module_name = left
        parsed = parse_json_mapping(right)
        if not parsed:
            raise PipelineError(f"Invalid --module-param '{raw}'. Expected module={{...}} when no key is provided")
        output.setdefault(module_name, {}).update(parsed)
    return output


def compact_json(value: Any, limit: int = 800) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    if len(text) <= limit:
        return text
    return text[: limit - 16].rstrip() + "\n... truncated ..."


def pct(value: Any) -> str:
    try:
        if value is None:
            return "n/a"
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def human_money(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "n/a"
    if number >= 1_000_000:
        return f"${number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"${number / 1_000:.1f}K"
    return f"${number:.0f}"


def short_text(value: Any, limit: int) -> str:
    if value is None:
        text = ""
    else:
        text = re.sub(r"\s+", " ", str(value).strip())
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def format_kv(label: str, value: Any, width: int) -> str:
    head = f"{label}: "
    max_value_len = max(width - len(head), 8)
    return head + short_text(value, max_value_len)


def ascii_box(title: str, lines: List[str], width: int = DEFAULT_CONSOLE_WIDTH) -> str:
    safe_width = max(width, 56)
    inner = safe_width - 4
    top = "+" + "-" * (safe_width - 2) + "+"
    title_line = "| " + short_text(title, inner).ljust(inner) + " |"
    body_lines = []
    for line in lines:
        body_lines.append("| " + short_text(line, inner).ljust(inner) + " |")
    if not body_lines:
        body_lines.append("| " + "".ljust(inner) + " |")
    return "\n".join([top, title_line, top, *body_lines, top])


def tokenize_terms(*parts: str) -> List[str]:
    tokens: List[str] = []
    seen = set()
    for part in parts:
        for token in re.findall(r"[a-z0-9]{3,}", (part or "").lower()):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def assess_feed_quality(
    news: Dict[str, Any],
    context: Dict[str, Any],
    headless_modules: List[str],
    extra_modules: Dict[str, Any],
) -> Dict[str, Any]:
    items = news.get("items") or []
    themes = news.get("themes") or []
    risk_rows = context.get("riskRows") or []
    module_count = len(set((headless_modules or []) + list((extra_modules or {}).keys())))
    recent_count = 0
    for item in items[:80]:
        dt = to_date(item.get("pubDateIso") or item.get("pubDate"))
        if dt and (now_utc() - dt).total_seconds() <= 72 * 3600:
            recent_count += 1

    score = 0
    notes: List[str] = []
    if len(items) >= 20:
        score += 30
    elif len(items) >= 10:
        score += 20
        notes.append("headline sample is thin; consider widening keywords or days")
    else:
        score += 10
        notes.append("headline sample is weak")

    if recent_count >= 8:
        score += 20
    elif recent_count >= 3:
        score += 12
        notes.append("few recent headlines in last 72h")
    else:
        notes.append("insufficient recent headline freshness")

    if len(themes) >= 3:
        score += 20
    elif len(themes) >= 1:
        score += 12
        notes.append("theme diversity is limited")

    if risk_rows:
        score += 15
    else:
        notes.append("risk score module returned no rows")

    if module_count >= 3:
        score += 15
    elif module_count == 2:
        score += 10
    else:
        score += 5
        notes.append("too few modules selected for robust monitoring")

    if score >= 75:
        status = "good"
    elif score >= 50:
        status = "moderate"
    else:
        status = "poor"

    if recent_count == 0 and status == "good":
        status = "moderate"
        notes.append("no recent items in last 72h; downgraded from good")

    return {
        "status": status,
        "score": score,
        "headline_count": len(items),
        "recent_headline_count_72h": recent_count,
        "theme_count": len(themes),
        "risk_row_count": len(risk_rows),
        "module_count": module_count,
        "notes": notes,
    }


def select_simulation_plan(
    config: Dict[str, Any],
    feed_quality: Dict[str, Any],
    runtime_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    runtime_overrides = runtime_overrides or {}
    mode = str(runtime_overrides.get("simulation_mode") or config.get("simulation_mode") or DEFAULT_SIMULATION_MODE).strip().lower()
    if mode not in {"auto", "manual"}:
        mode = DEFAULT_SIMULATION_MODE

    budget = runtime_overrides.get("budget_usd")
    if budget is None:
        budget = config.get("budget_usd", DEFAULT_BUDGET_USD)
    try:
        budget = max(0.0, float(budget))
    except (TypeError, ValueError):
        budget = DEFAULT_BUDGET_USD

    manual_rounds = runtime_overrides.get("target_rounds")
    if manual_rounds is None:
        manual_rounds = config.get("max_rounds", DEFAULT_MAX_ROUNDS)
    manual_profiles = runtime_overrides.get("target_profile_count")
    if manual_profiles is None:
        manual_profiles = config.get("parallel_profile_count", DEFAULT_PARALLEL_PROFILE_COUNT)
    manual_agents = runtime_overrides.get("target_agents")
    if manual_agents is None:
        manual_agents = config.get("target_agents") or 0

    rationale: List[str] = []
    if mode == "manual":
        selected_rounds = clamp_int(int(manual_rounds or DEFAULT_MAX_ROUNDS), 6, 240)
        selected_profiles = clamp_int(int(manual_profiles or DEFAULT_PARALLEL_PROFILE_COUNT), 2, 20)
        rationale.append("manual mode selected: using explicit operator controls")
    else:
        if budget <= 0.25:
            selected_rounds, selected_profiles = 12, 4
        elif budget <= 0.75:
            selected_rounds, selected_profiles = 20, 6
        elif budget <= 1.5:
            selected_rounds, selected_profiles = 28, 7
        elif budget <= 3.0:
            selected_rounds, selected_profiles = 42, 9
        else:
            selected_rounds, selected_profiles = 60, 11
        rationale.append(f"auto mode selected with budget ${budget:.2f}")

        quality = feed_quality.get("status")
        if quality == "good":
            selected_rounds += 4
            selected_profiles += 1
            rationale.append("feed quality good: increased simulation depth")
        elif quality == "poor":
            selected_rounds = max(10, selected_rounds - 6)
            selected_profiles = max(3, selected_profiles - 1)
            rationale.append("feed quality poor: reduced depth to avoid overfitting weak inputs")

    if manual_agents:
        try:
            agent_hint = clamp_int(int(manual_agents), 6, 240)
            selected_profiles = clamp_int(int(round(agent_hint / 6.0)), 2, 20)
            rationale.append(f"agent hint {agent_hint} translated to profile parallelism {selected_profiles}")
        except (TypeError, ValueError):
            agent_hint = 0
    else:
        agent_hint = 0

    selected_rounds = clamp_int(selected_rounds, 6, 240)
    selected_profiles = clamp_int(selected_profiles, 2, 20)
    return {
        "mode": mode,
        "budget_usd": budget,
        "requested": {
            "target_rounds": manual_rounds,
            "target_profile_count": manual_profiles,
            "target_agents": manual_agents,
        },
        "selected": {
            "max_rounds": selected_rounds,
            "parallel_profile_count": selected_profiles,
            "target_agents_hint": agent_hint,
        },
        "rationale": rationale,
    }


def request_json(method: str, url: str, *, timeout: tuple[int, int] = (10, 90), **kwargs: Any) -> Any:
    require_requests()
    headers = kwargs.pop("headers", {})
    merged_headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **headers,
    }
    response = requests.request(method, url, headers=merged_headers, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response.json()


def check_service(base_url: str, health_path: str = "/health") -> Dict[str, Any]:
    require_requests()
    url = f"{base_url.rstrip('/')}{health_path}"
    started = time.time()
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(5, 10))
        latency_ms = int((time.time() - started) * 1000)
        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "url": url,
            "body": response.text[:200],
        }
    except REQUEST_EXCEPTION as exc:
        latency_ms = int((time.time() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "url": url,
            "error": str(exc),
        }


def build_headless_url(base_url: str, modules: Iterable[str], params: Dict[str, Any]) -> str:
    from urllib.parse import urlencode

    query = {
        "modules": ",".join(modules),
        "format": "json",
        "params": json.dumps(params),
    }
    return f"{base_url.rstrip('/')}/api/headless?{urlencode(query)}"


def check_worldosint_service(base_url: str) -> Dict[str, Any]:
    require_requests()
    url = f"{base_url.rstrip('/')}/api/headless?module=list&format=json"
    started = time.time()
    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=(5, 15),
        )
        latency_ms = int((time.time() - started) * 1000)
        payload = response.json()
        modules = payload.get("modules") if isinstance(payload, dict) else None
        return {
            "ok": bool(response.ok and isinstance(modules, list) and modules),
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "url": url,
            "module_count": len(modules) if isinstance(modules, list) else 0,
        }
    except (REQUEST_EXCEPTION, ValueError) as exc:
        latency_ms = int((time.time() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "url": url,
            "error": str(exc),
        }


def fetch_worldosint_modules(base_url: str) -> Dict[str, Any]:
    require_requests()
    url = f"{base_url.rstrip('/')}/api/headless?module=list&format=json"
    started = time.time()
    response = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        timeout=(5, 20),
    )
    response.raise_for_status()
    latency_ms = int((time.time() - started) * 1000)
    payload = response.json() if response.content else {}
    modules = payload.get("modules") if isinstance(payload, dict) else []
    if not isinstance(modules, list):
        modules = []
    normalized: List[Dict[str, str]] = []
    for item in modules:
        if isinstance(item, str):
            normalized.append({"name": item, "description": ""})
            continue
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or item.get("module") or "").strip()
            if not name:
                continue
            normalized.append(
                {
                    "name": name,
                    "description": str(item.get("description") or item.get("desc") or "").strip(),
                }
            )
    normalized.sort(key=lambda row: row["name"].lower())
    return {
        "ok": True,
        "url": url,
        "latency_ms": latency_ms,
        "count": len(normalized),
        "modules": normalized,
    }


def build_feed_urls(topic: str, days: int) -> List[str]:
    encoded = quote(topic)
    return [
        f"https://news.google.com/rss/search?q={encoded}%20when%3A{days}d&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q=site%3Areuters.com%20{encoded}%20when%3A{days}d&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q=site%3Aapnews.com%20{encoded}%20when%3A{days}d&hl=en-US&gl=US&ceid=US:en",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://www.state.gov/feed/",
        "https://www.defense.gov/News/News-Stories/RSS/",
        "https://news.usni.org/feed",
    ]


def dedupe_news(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        key = f"{slugify(item.get('title', ''))}|{item.get('link', '')}"
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def relevant_news_items(items: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    if not keywords:
        return items
    filtered: List[Dict[str, Any]] = []
    for item in items:
        haystack = " ".join(
            str(item.get(field, ""))
            for field in ("title", "source", "link", "summary")
        ).lower()
        if any(keyword in haystack for keyword in keywords):
            filtered.append(item)
    return filtered


def fetch_news_snapshot(
    base_url: str,
    topic: str,
    days: int,
    keywords: List[str],
    module_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    feeds = build_feed_urls(topic, days)
    params = {
        "urls": feeds,
        "limit_per_feed": 25,
        "max_total": 250,
    }
    if module_params:
        params.update(module_params)
    url = build_headless_url(
        base_url,
        ["news_rss"],
        {
            "news_rss": params
        },
    )
    data = request_json("GET", url)
    raw_items = data.get("modules", {}).get("news_rss", {}).get("data", {}).get("items", [])
    items: List[Dict[str, Any]] = []
    for raw in raw_items:
        title = str(raw.get("title", "")).strip()
        if not title or raw.get("error"):
            continue
        pub_date = to_date(raw.get("pubDate"))
        items.append(
            {
                "title": title,
                "link": raw.get("link", ""),
                "source": raw.get("source", ""),
                "pubDate": raw.get("pubDate"),
                "pubDateIso": pub_date.isoformat() if pub_date else "",
            }
        )
    items.sort(key=lambda item: to_date(item.get("pubDateIso")) or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    items = dedupe_news(relevant_news_items(items, keywords))
    theme_counts = Counter(classify_theme(item.get("title", "")) for item in items)
    themes = [{"theme": theme, "count": count} for theme, count in theme_counts.most_common(8)]
    actors = extract_candidate_actors([item.get("title", "") for item in items], limit=12)
    return {
        "feeds": feeds,
        "items": items,
        "themes": themes,
        "actors": actors,
    }


def fetch_risk_and_posture(base_url: str, region_codes: List[str], theater_regions: List[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "riskRows": [],
        "usniArticleUrl": "",
        "usniArticleTitle": "",
        "theaterAssets": [],
    }
    url = build_headless_url(base_url, ["intelligence_risk_scores", "military_usni"], {})
    data = request_json("GET", url)

    scores = data.get("modules", {}).get("intelligence_risk_scores", {}).get("data", {}).get("ciiScores", [])
    if region_codes:
        selected = [row for row in scores if row.get("region") in set(region_codes)]
    else:
        selected = sorted(scores, key=lambda row: float(row.get("combinedScore") or 0), reverse=True)[:8]
    result["riskRows"] = selected

    report = data.get("modules", {}).get("military_usni", {}).get("data", {}).get("report", {})
    vessels = report.get("vessels") or []
    wanted_regions = set(theater_regions or THEATER_DEFAULTS)
    result["theaterAssets"] = [
        {
            "name": vessel.get("name"),
            "hullNumber": vessel.get("hullNumber"),
            "type": vessel.get("vesselType"),
            "region": vessel.get("region"),
            "status": vessel.get("deploymentStatus"),
            "articleUrl": vessel.get("articleUrl"),
        }
        for vessel in vessels
        if not wanted_regions or vessel.get("region") in wanted_regions
    ][:12]
    result["usniArticleUrl"] = report.get("articleUrl", "")
    result["usniArticleTitle"] = report.get("articleTitle", "")
    return result


def fetch_additional_modules(base_url: str, modules: List[str], module_params: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    names = dedupe_strings(modules)
    if not names:
        return {}
    params = {name: module_params.get(name, {}) for name in names if module_params.get(name)}
    url = build_headless_url(base_url, names, params)
    data = request_json("GET", url)
    payload = data.get("modules")
    return payload if isinstance(payload, dict) else {}


def topic_match_score(text: str, terms: List[str]) -> float:
    haystack = (text or "").lower()
    if not haystack or not terms:
        return 0.0
    matches = sum(1 for term in terms if term in haystack)
    return matches / max(len(terms), 1)


def market_deadline_days(end_date: Any) -> float:
    dt = to_date(end_date)
    if not dt:
        return 9999.0
    return (dt - now_utc()).total_seconds() / 86400.0


def score_market(market: Dict[str, Any], terms: List[str], max_deadline_days: int) -> float:
    text = " ".join(
        str(market.get(field, ""))
        for field in ("question", "description", "title")
    )
    match = topic_match_score(text, terms) * 12
    deadline_days = market_deadline_days(market.get("endDate"))
    if deadline_days < 0 or deadline_days > max_deadline_days:
        return -1e9
    deadline_bonus = (max_deadline_days - deadline_days) / max(max_deadline_days, 1) * 2
    volume_bonus = math.log10(float(market.get("volumeNum") or 0) + 1)
    liquidity_bonus = math.log10(float(market.get("liquidityNum") or 0) + 1)
    clarity_bonus = 1.0 if str(market.get("question", "")).strip().endswith("?") else 0.0
    return match + deadline_bonus + volume_bonus + liquidity_bonus + clarity_bonus


def search_markets(query: str, max_deadline_days: int) -> List[Dict[str, Any]]:
    data = request_json("GET", f"{GAMMA_API}/public-search?q={quote(query)}")
    events = data.get("events", [])
    seen = set()
    candidates: List[Dict[str, Any]] = []
    terms = tokenize_terms(query)
    for event in events:
        title = event.get("title", "")
        for market in event.get("markets") or []:
            slug = market.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            if market.get("closed") or market.get("active") is False:
                continue
            outcomes = parse_json_list(market.get("outcomes"))
            token_ids = parse_json_list(market.get("clobTokenIds"))
            if len(outcomes) not in (0, 2) or len(token_ids) not in (0, 2):
                continue
            market_copy = dict(market)
            market_copy["title"] = title
            market_copy["score"] = score_market(market_copy, terms, max_deadline_days)
            if market_copy["score"] <= -1e8:
                continue
            candidates.append(market_copy)
    candidates.sort(key=lambda market: market.get("score", 0), reverse=True)
    return candidates


def enrich_market(slug: str) -> Dict[str, Any]:
    rows = request_json("GET", f"{GAMMA_API}/markets?active=true&closed=false&slug={quote(slug)}")
    if not rows:
        raise PipelineError(f"Polymarket market not found for slug: {slug}")
    market = dict(rows[0])
    token_ids = parse_json_list(market.get("clobTokenIds"))
    best_bid = market.get("bestBid")
    best_ask = market.get("bestAsk")
    spread = None
    try:
        best_bid = float(best_bid) if best_bid is not None else None
    except (TypeError, ValueError):
        best_bid = None
    try:
        best_ask = float(best_ask) if best_ask is not None else None
    except (TypeError, ValueError):
        best_ask = None
    if best_bid is not None and best_ask is not None:
        spread = round(best_ask - best_bid, 4)
    if (best_bid is None or best_ask is None) and token_ids:
        try:
            book = request_json("GET", f"{CLOB_API}/book?token_id={quote(str(token_ids[0]))}")
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            best_bid = float(bids[0]["price"]) if bids else None
            best_ask = float(asks[0]["price"]) if asks else None
            if best_bid is not None and best_ask is not None:
                spread = round(best_ask - best_bid, 4)
        except REQUEST_EXCEPTION:
            pass
    if best_bid is None or best_ask is None:
        prices = parse_json_list(market.get("outcomePrices"))
        midpoint = float(prices[0]) if prices else float(market.get("lastTradePrice") or 0)
        best_bid = midpoint
        best_ask = midpoint
        spread = 0.0
    return {
        "slug": market.get("slug"),
        "question": str(market.get("question") or "").strip(),
        "description": str(market.get("description") or "").strip(),
        "url": f"https://polymarket.com/event/{market.get('slug')}",
        "endDate": market.get("endDate"),
        "volumeNum": float(market.get("volumeNum") or 0),
        "liquidityNum": float(market.get("liquidityNum") or market.get("liquidityClob") or 0),
        "bestBid": best_bid,
        "bestAsk": best_ask,
        "spread": spread,
        "acceptingOrders": bool(market.get("acceptingOrders")),
        "conditionId": market.get("conditionId"),
        "clobTokenIds": token_ids,
        "outcomes": parse_json_list(market.get("outcomes")),
        "outcomePrices": parse_json_list(market.get("outcomePrices")),
        "lastTradePrice": float(market.get("lastTradePrice") or 0),
    }


def select_markets(query: str, max_deadline_days: int, limit: int = 5) -> List[Dict[str, Any]]:
    candidates = search_markets(query, max_deadline_days)
    if not candidates:
        raise PipelineError(f"No open Polymarket markets matched query '{query}' within {max_deadline_days} days")
    selected: List[Dict[str, Any]] = []
    for candidate in candidates[: max(limit * 2, limit)]:
        try:
            selected.append(enrich_market(candidate["slug"]))
        except Exception:
            continue
        if len(selected) >= limit:
            break
    if not selected:
        raise PipelineError(f"Failed to enrich any candidate markets for query '{query}'")
    selected.sort(key=lambda market: market_deadline_days(market.get("endDate")))
    return selected


def classify_theme(title: str) -> str:
    text = (title or "").lower()
    if re.search(r"hormuz|gulf|shipping|escort|oil|port|navy", text):
        return "Shipping and energy"
    if re.search(r"deal|talks|ceasefire|diplomacy|enrichment|nuclear|iaea|inspection", text):
        return "Diplomacy and nuclear file"
    if re.search(r"cyber|blackout|internet", text):
        return "Cyber and information control"
    if re.search(r"regime|leader|protest|succession", text):
        return "Regime stability"
    if re.search(r"strike|missile|drone|attack|offensive|war", text):
        return "Kinetic conflict"
    return "General conflict"


def extract_candidate_actors(texts: List[str], limit: int = 10) -> List[Dict[str, Any]]:
    counts: Counter[str] = Counter()
    for text in texts:
        for match in CAPITALIZED_PHRASE_RE.findall(text or ""):
            phrase = match.strip()
            if not phrase or phrase in SOURCE_STOPWORDS:
                continue
            if phrase.lower() in {"yes", "no", "will", "what", "when"}:
                continue
            counts[phrase] += 1
    return [
        {"label": label, "count": count}
        for label, count in counts.most_common(limit)
    ]


def split_description_points(description: str, limit: int = 4) -> List[str]:
    if not description:
        return []
    normalized = re.sub(r"\s+", " ", description.strip())
    chunks = re.split(r"(?<=[.!?])\s+", normalized)
    output = []
    for chunk in chunks:
        chunk = chunk.strip(" -")
        if len(chunk) < 20:
            continue
        output.append(chunk)
        if len(output) >= limit:
            break
    return output


def generate_simulation_requirement(topic: str, primary_market: Dict[str, Any]) -> str:
    deadline = short_dt(primary_market.get("endDate"))
    question = primary_market.get("question", "")
    return (
        f"Forecast whether the Polymarket contract '{question}' resolves YES by {deadline}. "
        f"Use the seed packet to simulate the geopolitical topic '{topic}', actor incentives, escalation pathways, "
        f"diplomatic pathways, and the exact evidence threshold implied by the market wording and description. "
        f"End with an explicit YES/NO call for the contract plus the milestones that would most change the forecast."
    )


def build_seed_markdown(
    topic_id: str,
    topic: str,
    query: str,
    keywords: List[str],
    markets: List[Dict[str, Any]],
    news: Dict[str, Any],
    context: Dict[str, Any],
    extra_modules: Dict[str, Any],
    generated_at: str,
    base_url: str,
    headless_modules: List[str],
) -> str:
    primary_market = markets[0]
    related_markets = markets[1:]
    lines: List[str] = []
    lines.append(f"# MiroFish Seed Packet: {topic}")
    lines.append("")
    lines.append(f"Generated at: {generated_at}")
    lines.append(f"Tracked topic id: {topic_id}")
    lines.append(f"Market query: {query}")
    lines.append(f"WorldOSINT base: {base_url}")
    lines.append(f"Configured WorldOSINT modules: {', '.join(headless_modules)}")
    lines.append("")
    lines.append("## Primary contract")
    lines.append("")
    lines.append(f"- Market: {primary_market['question']}")
    lines.append(f"- URL: {primary_market['url']}")
    lines.append(f"- Deadline: {short_dt(primary_market['endDate'])}")
    lines.append(f"- Best bid / ask: {pct(primary_market['bestBid'])} / {pct(primary_market['bestAsk'])}")
    lines.append(f"- Liquidity / volume: {human_money(primary_market['liquidityNum'])} / {human_money(primary_market['volumeNum'])}")
    lines.append("")
    description_points = split_description_points(primary_market.get("description", ""))
    if description_points:
        lines.append("Resolution / description notes:")
        for point in description_points:
            lines.append(f"- {point}")
        lines.append("")
    else:
        lines.append("Resolution note:")
        lines.append("- Verify the market page for exact resolution language before making a binary call.")
        lines.append("")
    if related_markets:
        lines.append("## Related open markets")
        lines.append("")
        lines.append("| Market | Bid | Ask | Deadline |")
        lines.append("| --- | --- | --- | --- |")
        for market in related_markets:
            lines.append(f"| {market['question']} | {pct(market['bestBid'])} | {pct(market['bestAsk'])} | {short_dt(market['endDate'])} |")
        lines.append("")
    lines.append("## Situation snapshot")
    lines.append("")
    lines.append(f"- Relevant RSS headlines collected: {len(news['items'])}")
    lines.append(f"- Keyword set: {', '.join(keywords) if keywords else 'auto-derived'}")
    lines.append(f"- Official / defense feeds monitored: {sum(1 for feed in news['feeds'] if 'state.gov' in feed or 'defense.gov' in feed or 'usni' in feed)}")
    lines.append("")
    if news.get("themes"):
        lines.append("Dominant themes:")
        for theme in news["themes"][:6]:
            lines.append(f"- {theme['theme']}: {theme['count']} headlines")
        lines.append("")
    actor_rows = news.get("actors") or []
    if actor_rows:
        lines.append("## Candidate actors from headlines and market text")
        lines.append("")
        for actor in actor_rows[:10]:
            lines.append(f"- {actor['label']}: {actor['count']} mentions")
        lines.append("")
    if context.get("riskRows"):
        lines.append("## WorldOSINT monitoring signals")
        lines.append("")
        lines.append("| Region | Combined risk | Static baseline | Dynamic score | Trend |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in context["riskRows"]:
            lines.append(
                f"| {row.get('region', 'n/a')} | {row.get('combinedScore', 'n/a')} | {row.get('staticBaseline', 'n/a')} | {row.get('dynamicScore', 'n/a')} | {str(row.get('trend', '')).replace('TREND_DIRECTION_', '')} |"
            )
        lines.append("")
    if context.get("usniArticleUrl"):
        lines.append(f"- USNI posture source: [{context.get('usniArticleTitle') or 'USNI Fleet Tracker'}]({context['usniArticleUrl']})")
    for asset in context.get("theaterAssets", [])[:12]:
        lines.append(f"- {asset.get('name')} ({asset.get('hullNumber') or 'n/a'}, {asset.get('type')}) in {asset.get('region')}, status={asset.get('status')}")
    if context.get("theaterAssets"):
        lines.append("")
    if extra_modules:
        lines.append("## Additional WorldOSINT module snapshots")
        lines.append("")
        for module_name, payload in list(extra_modules.items())[:8]:
            data = payload.get("data") if isinstance(payload, dict) else payload
            keys = list(data.keys())[:8] if isinstance(data, dict) else []
            lines.append(f"### {module_name}")
            lines.append("")
            if keys:
                lines.append(f"- Top-level keys: {', '.join(keys)}")
            lines.append("```json")
            lines.append(compact_json(data, limit=1000))
            lines.append("```")
            lines.append("")
    lines.append("## Recent headlines")
    lines.append("")
    for item in news["items"][:20]:
        lines.append(f"- {short_dt(item.get('pubDateIso') or item.get('pubDate'))} | {item.get('source') or 'Unknown source'} | [{item.get('title')}]({item.get('link')})")
    lines.append("")
    lines.append("## MiroFish simulation brief")
    lines.append("")
    lines.append(f"Use this packet to simulate whether the primary contract resolves Yes before {short_dt(primary_market['endDate'])}.")
    lines.append("")
    lines.append("Questions the simulation should answer:")
    lines.append(f"- What sequence of events could still produce a Yes resolution for '{primary_market['question']}'?")
    lines.append("- Which actors are central, what are their incentives, and which actions are realistic in the time remaining?")
    lines.append("- Which escalation paths, diplomatic paths, or verification milestones most change the contract odds?")
    lines.append("- What observable milestones would move this from low-probability to live, or vice versa?")
    lines.append("")
    lines.append("Suggested scoring approach inside the simulation:")
    lines.append("- Base case: the contract does not resolve Yes by the deadline unless a concrete public milestone appears.")
    lines.append("- Upside path: official statements, negotiation framework, inspections, compliance concessions, mediator activity.")
    lines.append("- Downside path: escalation, verification failure, military signaling, domestic hardening, deadline slippage.")
    lines.append("- Evidence threshold for Yes: public official announcement or overwhelming credible reporting consistent with the market description.")
    lines.append("")
    lines.append("## Source notes")
    lines.append("")
    lines.append("- RSS feeds were fetched through the local WorldOSINT headless `news_rss` module.")
    lines.append("- Risk scores and naval posture came from WorldOSINT headless `intelligence_risk_scores` and `military_usni` modules.")
    if extra_modules:
        lines.append(f"- Additional WorldOSINT modules included: {', '.join(extra_modules.keys())}.")
    lines.append("- Market metadata came from Polymarket Gamma API; top-of-book pricing came from the CLOB book endpoint where available.")
    lines.append("")
    lines.append("Reference URLs:")
    for market in markets:
        lines.append(f"- [Polymarket: {market['question']}]({market['url']})")
    if context.get("usniArticleUrl"):
        lines.append(f"- [USNI Fleet Tracker source]({context['usniArticleUrl']})")
    return "\n".join(lines) + "\n"


def poll_task(base_url: str, task_id: str, *, timeout_seconds: int = 1800, sleep_seconds: int = 5) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_payload: Dict[str, Any] = {}
    while time.time() < deadline:
        payload = request_json("GET", f"{base_url.rstrip('/')}/api/graph/task/{task_id}")
        data = payload.get("data") or {}
        last_payload = data
        status = data.get("status")
        if status == "completed":
            return data
        if status == "failed":
            raise PipelineError(data.get("error") or f"Task {task_id} failed")
        time.sleep(sleep_seconds)
    raise PipelineError(f"Timed out waiting for task {task_id}")


def poll_prepare(base_url: str, simulation_id: str, task_id: str, *, timeout_seconds: int = 1800, sleep_seconds: int = 5) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        payload = request_json(
            "POST",
            f"{base_url.rstrip('/')}/api/simulation/prepare/status",
            json={"simulation_id": simulation_id, "task_id": task_id},
        )
        data = payload.get("data") or {}
        status = data.get("status")
        if status in {"completed", "ready"}:
            return data
        if status == "failed":
            raise PipelineError(data.get("error") or f"Prepare task {task_id} failed")
        time.sleep(sleep_seconds)
    raise PipelineError(f"Timed out waiting for prepare task {task_id}")


def poll_run(base_url: str, simulation_id: str, *, timeout_seconds: int = 3600, sleep_seconds: int = 10) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        payload = request_json("GET", f"{base_url.rstrip('/')}/api/simulation/{simulation_id}/run-status")
        data = payload.get("data") or {}
        status = data.get("runner_status")
        if status in {"completed", "stopped", "failed"}:
            return data
        time.sleep(sleep_seconds)
    raise PipelineError(f"Timed out waiting for simulation {simulation_id}")


def parse_action_log(path: Path) -> Dict[str, Any]:
    event_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    agents: Counter[str] = Counter()
    if not path.exists():
        return {
            "lines": 0,
            "event_counts": {},
            "action_counts": {},
            "top_agents": [],
        }
    lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            lines += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = payload.get("event_type", "unknown")
            event_counts[event_type] += 1
            action_type = payload.get("action_type")
            if action_type:
                action_counts[action_type] += 1
                agents[payload.get("agent_name", "unknown")] += 1
    return {
        "lines": lines,
        "event_counts": dict(event_counts),
        "action_counts": dict(action_counts.most_common()),
        "top_agents": agents.most_common(10),
    }


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def extract_primary_question(config: Dict[str, Any]) -> str:
    requirement = str(config.get("simulation_requirement") or "").strip()
    if not requirement:
        return ""
    match = re.search(r"contract '([^']+)'", requirement)
    if match:
        return match.group(1).strip()
    match = re.search(r'contract "([^"]+)"', requirement)
    if match:
        return match.group(1).strip()
    return requirement.splitlines()[0][:200].strip()


def normalize_lookup_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def extract_injected_actors(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for agent in config.get("agent_configs") or []:
        if not isinstance(agent, dict):
            continue
        is_counterfactual = bool(agent.get("counterfactual")) or agent.get("injection_round") is not None
        entity_uuid = str(agent.get("entity_uuid") or "")
        if not is_counterfactual and not entity_uuid.startswith("counterfactual_"):
            continue
        output.append(
            {
                "agent_id": agent.get("agent_id"),
                "name": agent.get("entity_name"),
                "entity_type": agent.get("entity_type"),
                "stance": agent.get("stance"),
                "injection_round": agent.get("injection_round"),
                "influence_weight": agent.get("influence_weight"),
                "activity_level": agent.get("activity_level"),
            }
        )
    return output


def build_simulation_index_entry(sim_dir: Path, include_actions: bool = False) -> Optional[Dict[str, Any]]:
    config_path = sim_dir / "simulation_config.json"
    state_path = sim_dir / "state.json"
    if not config_path.exists() and not state_path.exists():
        return None

    config = load_json_file(config_path)
    state = load_json_file(state_path)
    counterfactual = config.get("counterfactual") if isinstance(config.get("counterfactual"), dict) else {}
    injected_actors = extract_injected_actors(config)
    question = extract_primary_question(config)
    twitter_log = sim_dir / "twitter" / "actions.jsonl"
    reddit_log = sim_dir / "reddit" / "actions.jsonl"

    twitter_summary = parse_action_log(twitter_log) if include_actions else {"lines": 0}
    reddit_summary = parse_action_log(reddit_log) if include_actions else {"lines": 0}

    return {
        "simulation_id": sim_dir.name,
        "project_id": config.get("project_id") or state.get("project_id"),
        "graph_id": config.get("graph_id") or state.get("graph_id"),
        "status": state.get("status"),
        "question": question,
        "simulation_requirement": str(config.get("simulation_requirement") or "").strip(),
        "counterfactual": {
            "enabled": bool(counterfactual),
            "base_simulation_id": counterfactual.get("base_simulation_id"),
            "injection_round": counterfactual.get("injection_round"),
            "opening_statement": counterfactual.get("opening_statement"),
        },
        "injected_actors": injected_actors,
        "artifact_paths": {
            "simulation_dir": str(sim_dir),
            "config_path": str(config_path),
            "state_path": str(state_path),
            "twitter_log": str(twitter_log),
            "reddit_log": str(reddit_log),
        },
        "twitter_actions": twitter_summary.get("lines", 0),
        "reddit_actions": reddit_summary.get("lines", 0),
        "agent_count": len(config.get("agent_configs") or []),
        "updated_at": state.get("updated_at") or config.get("generated_at"),
    }


def iter_simulation_entries(mirofish_root: Path, include_actions: bool = False) -> Iterable[Dict[str, Any]]:
    simulation_root = mirofish_root / "backend" / "uploads" / "simulations"
    if not simulation_root.exists():
        raise PipelineError(f"MiroFish simulation directory not found: {simulation_root}")
    for sim_dir in sorted(simulation_root.iterdir(), key=lambda path: path.name, reverse=True):
        if not sim_dir.is_dir():
            continue
        entry = build_simulation_index_entry(sim_dir, include_actions=include_actions)
        if entry:
            yield entry


def entry_search_blob(entry: Dict[str, Any]) -> str:
    parts = [
        entry.get("simulation_id"),
        entry.get("project_id"),
        entry.get("graph_id"),
        entry.get("status"),
        entry.get("question"),
        entry.get("simulation_requirement"),
        (entry.get("counterfactual") or {}).get("base_simulation_id"),
    ]
    for actor in entry.get("injected_actors") or []:
        parts.extend(
            [
                actor.get("name"),
                actor.get("entity_type"),
                actor.get("stance"),
                actor.get("injection_round"),
            ]
        )
    return normalize_lookup_text(" ".join(str(part or "") for part in parts))


def select_matching_actors(entry: Dict[str, Any], actor_query: str) -> List[Dict[str, Any]]:
    needle = normalize_lookup_text(actor_query)
    if not needle:
        return []
    matches = []
    for actor in entry.get("injected_actors") or []:
        haystack = normalize_lookup_text(" ".join(str(actor.get(key) or "") for key in ("name", "entity_type", "stance")))
        if needle in haystack:
            matches.append(actor)
    return matches


def score_entry_match(entry: Dict[str, Any], query_tokens: List[str]) -> int:
    if not query_tokens:
        return 0
    score = 0
    search_blob = entry_search_blob(entry)
    simulation_id = normalize_lookup_text(entry.get("simulation_id"))
    base_simulation_id = normalize_lookup_text((entry.get("counterfactual") or {}).get("base_simulation_id"))
    question = normalize_lookup_text(entry.get("question"))
    for token in query_tokens:
        if token == simulation_id:
            score += 30
        elif simulation_id and token in simulation_id:
            score += 20
        if token == base_simulation_id:
            score += 18
        elif base_simulation_id and token in base_simulation_id:
            score += 10
        if token and token in question:
            score += 8
        score += search_blob.count(token)
    return score


def summarize_simulation_run(run_dir: Path, mirofish_root: Path, simulation_id: str, market: Dict[str, Any], topic: str) -> Dict[str, Any]:
    sim_dir = mirofish_root / "backend" / "uploads" / "simulations" / simulation_id
    config_path = sim_dir / "simulation_config.json"
    log_path = sim_dir / "simulation.log"
    twitter_log = sim_dir / "twitter" / "actions.jsonl"
    reddit_log = sim_dir / "reddit" / "actions.jsonl"

    config: Dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)

    twitter = parse_action_log(twitter_log)
    reddit = parse_action_log(reddit_log)

    summary = {
        "simulation_id": simulation_id,
        "simulation_dir": str(sim_dir),
        "config_path": str(config_path),
        "log_path": str(log_path),
        "twitter_log": str(twitter_log),
        "reddit_log": str(reddit_log),
        "agent_count": len(config.get("agents", [])),
        "initial_posts": len(config.get("events", {}).get("initial_posts", [])),
        "hours": config.get("time", {}).get("total_hours"),
        "twitter": twitter,
        "reddit": reddit,
    }

    lines = []
    lines.append(f"# Hermes MiroFish Run Summary: {topic}")
    lines.append("")
    lines.append(f"Generated at: {iso_now()}")
    lines.append(f"Primary market: {market['question']}")
    lines.append(f"Simulation ID: `{simulation_id}`")
    lines.append(f"Simulation directory: `{sim_dir}`")
    lines.append("")
    lines.append("## Runtime")
    lines.append("")
    lines.append(f"- Agents: {summary['agent_count']}")
    lines.append(f"- Initial posts: {summary['initial_posts']}")
    lines.append(f"- Configured hours: {summary['hours']}")
    lines.append("")
    lines.append("## Twitter")
    lines.append("")
    lines.append(f"- Action log lines: {twitter['lines']}")
    for name, count in twitter["action_counts"].items():
        lines.append(f"- {name}: {count}")
    if twitter["top_agents"]:
        lines.append("- Top agents: " + ", ".join(f"{name} ({count})" for name, count in twitter["top_agents"][:5]))
    lines.append("")
    lines.append("## Reddit")
    lines.append("")
    lines.append(f"- Action log lines: {reddit['lines']}")
    for name, count in reddit["action_counts"].items():
        lines.append(f"- {name}: {count}")
    if reddit["top_agents"]:
        lines.append("- Top agents: " + ", ".join(f"{name} ({count})" for name, count in reddit["top_agents"][:5]))
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- Config: `{config_path}`")
    lines.append(f"- Main log: `{log_path}`")
    lines.append(f"- Twitter actions: `{twitter_log}`")
    lines.append(f"- Reddit actions: `{reddit_log}`")

    summary_path = run_dir / "simulation_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def run_mirofish_pipeline(
    *,
    topic: str,
    seed_path: Path,
    primary_market: Dict[str, Any],
    mirofish_base_url: str,
    mirofish_root: Path,
    platform: str,
    max_rounds: int,
    use_llm_for_profiles: bool,
    parallel_profile_count: int,
    enable_graph_memory_update: bool,
    generate_report: bool,
    run_dir: Path,
) -> Dict[str, Any]:
    require_requests()
    requirement = generate_simulation_requirement(topic, primary_market)
    mime_type = mimetypes.guess_type(seed_path.name)[0] or "text/markdown"
    with seed_path.open("rb") as handle:
        ontology_payload = requests.post(
            f"{mirofish_base_url.rstrip('/')}/api/graph/ontology/generate",
            data={
                "simulation_requirement": requirement,
                "project_name": f"Hermes {topic} {seed_path.parent.name}",
            },
            files={"files": (seed_path.name, handle, mime_type)},
            headers={"User-Agent": USER_AGENT},
            timeout=(10, 300),
        )
    ontology_payload.raise_for_status()
    ontology_data = ontology_payload.json().get("data") or {}
    project_id = ontology_data.get("project_id")
    if not project_id:
        raise PipelineError("MiroFish ontology generation did not return a project_id")

    build_payload = request_json(
        "POST",
        f"{mirofish_base_url.rstrip('/')}/api/graph/build",
        json={"project_id": project_id},
    )
    build_task_id = build_payload.get("data", {}).get("task_id")
    if not build_task_id:
        raise PipelineError("MiroFish graph build did not return a task_id")
    build_task = poll_task(mirofish_base_url, build_task_id)
    graph_id = (build_task.get("result") or {}).get("graph_id")
    if not graph_id:
        project_payload = request_json("GET", f"{mirofish_base_url.rstrip('/')}/api/graph/project/{project_id}")
        graph_id = (project_payload.get("data") or {}).get("graph_id")
    if not graph_id:
        raise PipelineError("MiroFish graph build completed but graph_id is missing")

    create_payload = request_json(
        "POST",
        f"{mirofish_base_url.rstrip('/')}/api/simulation/create",
        json={
            "project_id": project_id,
            "graph_id": graph_id,
            "enable_twitter": platform in {"twitter", "parallel"},
            "enable_reddit": platform in {"reddit", "parallel"},
        },
    )
    simulation_id = (create_payload.get("data") or {}).get("simulation_id")
    if not simulation_id:
        raise PipelineError("MiroFish simulation creation did not return simulation_id")

    prepare_payload = request_json(
        "POST",
        f"{mirofish_base_url.rstrip('/')}/api/simulation/prepare",
        json={
            "simulation_id": simulation_id,
            "use_llm_for_profiles": use_llm_for_profiles,
            "parallel_profile_count": parallel_profile_count,
        },
    )
    prepare_data = prepare_payload.get("data") or {}
    prepare_task_id = prepare_data.get("task_id")
    if prepare_task_id:
        poll_prepare(mirofish_base_url, simulation_id, prepare_task_id)
    elif prepare_data.get("status") not in {"ready"}:
        raise PipelineError("MiroFish prepare did not return a task_id or ready status")

    start_payload = request_json(
        "POST",
        f"{mirofish_base_url.rstrip('/')}/api/simulation/start",
        json={
            "simulation_id": simulation_id,
            "platform": platform,
            "max_rounds": max_rounds,
            "enable_graph_memory_update": enable_graph_memory_update,
        },
    )
    run_state = poll_run(mirofish_base_url, simulation_id)

    report_data: Dict[str, Any] = {}
    if generate_report:
        report_payload = request_json(
            "POST",
            f"{mirofish_base_url.rstrip('/')}/api/report/generate",
            json={"simulation_id": simulation_id},
        )
        report_data = report_payload.get("data") or {}

    summary = summarize_simulation_run(run_dir, mirofish_root, simulation_id, primary_market, topic)
    return {
        "project_id": project_id,
        "graph_id": graph_id,
        "graph_task_id": build_task_id,
        "prepare_task_id": prepare_task_id,
        "simulation_id": simulation_id,
        "start_data": start_payload.get("data") or {},
        "run_state": run_state,
        "report": report_data,
        "summary": summary,
    }


def run_topic(
    config: Dict[str, Any],
    *,
    simulate: bool,
    generate_report: bool,
    runtime_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    topic_id = config["topic_id"]
    topic = config["topic"]
    market_query = config.get("market_query") or topic
    keywords = config.get("keywords") or tokenize_terms(topic, market_query)
    region_codes = config.get("region_codes") or []
    theater_regions = config.get("theater_regions") or THEATER_DEFAULTS
    worldosint_base = config.get("worldosint_base_url") or DEFAULT_WORLDOSINT_BASE
    mirofish_base = config.get("mirofish_base_url") or DEFAULT_MIROFISH_BASE
    mirofish_root = resolve_mirofish_root(config.get("mirofish_root") or DEFAULT_MIROFISH_ROOT)
    days = int(config.get("days") or DEFAULT_DAYS)
    max_deadline_days = int(config.get("max_deadline_days") or DEFAULT_MAX_DEADLINE_DAYS)
    platform = config.get("platform") or DEFAULT_PLATFORM
    max_rounds = int(config.get("max_rounds") or DEFAULT_MAX_ROUNDS)
    use_llm_for_profiles = bool(config.get("use_llm_for_profiles", False))
    parallel_profile_count = int(config.get("parallel_profile_count") or DEFAULT_PARALLEL_PROFILE_COUNT)
    enable_graph_memory_update = bool(config.get("enable_graph_memory_update", False))
    headless_modules = normalize_headless_modules(config.get("headless_modules"))
    module_params = normalize_module_params(config.get("module_params"))

    timestamp = now_utc().strftime("%Y%m%d_%H%M%S")
    run_dir = DATA_DIR / "runs" / topic_id / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    world_status = check_worldosint_service(worldosint_base)
    mirofish_status = check_service(mirofish_base, "/health")
    if not world_status["ok"]:
        raise PipelineError(f"WorldOSINT is unavailable: {world_status}")
    if simulate and not mirofish_status["ok"]:
        raise PipelineError(f"MiroFish backend is unavailable: {mirofish_status}")

    markets = select_markets(market_query, max_deadline_days)
    news = {"feeds": [], "items": [], "themes": [], "actors": []}
    if "news_rss" in headless_modules:
        news = fetch_news_snapshot(worldosint_base, topic, days, keywords, module_params.get("news_rss"))
    context = {"riskRows": [], "usniArticleUrl": "", "usniArticleTitle": "", "theaterAssets": []}
    if "intelligence_risk_scores" in headless_modules or "military_usni" in headless_modules:
        try:
            context = fetch_risk_and_posture(worldosint_base, region_codes, theater_regions)
        except Exception as exc:
            context = {"riskRows": [], "usniArticleUrl": "", "usniArticleTitle": "", "theaterAssets": [], "warning": str(exc)}
    built_in_modules = {"news_rss", "intelligence_risk_scores", "military_usni"}
    extra_modules = fetch_additional_modules(
        worldosint_base,
        [name for name in headless_modules if name not in built_in_modules],
        module_params,
    )
    feed_quality = assess_feed_quality(news, context, headless_modules, extra_modules)
    simulation_plan = select_simulation_plan(config, feed_quality, runtime_overrides=runtime_overrides)
    selected_rounds = int(simulation_plan["selected"]["max_rounds"])
    selected_profiles = int(simulation_plan["selected"]["parallel_profile_count"])
    require_feed_confirmation = bool((runtime_overrides or {}).get("require_feed_confirmation", False))
    if simulate and require_feed_confirmation and feed_quality.get("status") == "poor":
        raise PipelineError(
            f"Feed confirmation failed: quality is poor (score={feed_quality.get('score')}). "
            "Adjust modules/keywords or run without --require-feed-confirmation."
        )

    generated_at = iso_now()
    seed_markdown = build_seed_markdown(
        topic_id,
        topic,
        market_query,
        keywords,
        markets,
        news,
        context,
        extra_modules,
        generated_at,
        worldosint_base,
        headless_modules,
    )
    seed_path = run_dir / f"{topic_id}_seed.md"
    snapshot_path = run_dir / f"{topic_id}_snapshot.json"
    seed_path.write_text(seed_markdown, encoding="utf-8")

    snapshot = {
        "generated_at": generated_at,
        "topic_id": topic_id,
        "topic": topic,
        "market_query": market_query,
        "keywords": keywords,
        "headless_modules": headless_modules,
        "module_params": module_params,
        "worldosint_base_url": worldosint_base,
        "mirofish_base_url": mirofish_base,
        "markets": markets,
        "news": news,
        "context": context,
        "extra_modules": extra_modules,
        "feed_quality": feed_quality,
        "simulation_plan": simulation_plan,
        "seed_path": str(seed_path),
        "simulate": simulate,
    }
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    result: Dict[str, Any] = {
        "topic_id": topic_id,
        "topic": topic,
        "run_dir": str(run_dir),
        "seed_path": str(seed_path),
        "snapshot_path": str(snapshot_path),
        "primary_market": markets[0],
        "related_markets": markets[1:],
        "worldosint_status": world_status,
        "mirofish_status": mirofish_status,
        "feed_quality": feed_quality,
        "simulation_plan": simulation_plan,
    }

    if simulate:
        result["mirofish"] = run_mirofish_pipeline(
            topic=topic,
            seed_path=seed_path,
            primary_market=markets[0],
            mirofish_base_url=mirofish_base,
            mirofish_root=mirofish_root,
            platform=platform,
            max_rounds=selected_rounds,
            use_llm_for_profiles=use_llm_for_profiles,
            parallel_profile_count=selected_profiles,
            enable_graph_memory_update=enable_graph_memory_update,
            generate_report=generate_report,
            run_dir=run_dir,
        )

    summary_lines = []
    summary_lines.append(f"# Hermes Pipeline Run: {topic}")
    summary_lines.append("")
    summary_lines.append(f"Generated at: {generated_at}")
    summary_lines.append(f"Run directory: `{run_dir}`")
    summary_lines.append("")
    summary_lines.append("## Primary market")
    summary_lines.append("")
    summary_lines.append(f"- {markets[0]['question']}")
    summary_lines.append(f"- Bid / ask: {pct(markets[0]['bestBid'])} / {pct(markets[0]['bestAsk'])}")
    summary_lines.append(f"- Deadline: {short_dt(markets[0]['endDate'])}")
    summary_lines.append(f"- URL: {markets[0]['url']}")
    summary_lines.append(f"- WorldOSINT modules: {', '.join(headless_modules)}")
    summary_lines.append(f"- Feed quality: {feed_quality.get('status')} (score={feed_quality.get('score')})")
    summary_lines.append(
        f"- Simulation plan: mode={simulation_plan.get('mode')} rounds={selected_rounds} profiles={selected_profiles} budget=${simulation_plan.get('budget_usd'):.2f}"
    )
    summary_lines.append("")
    summary_lines.append("## Artifacts")
    summary_lines.append("")
    summary_lines.append(f"- Seed packet: `{seed_path}`")
    summary_lines.append(f"- Raw snapshot: `{snapshot_path}`")
    if simulate:
        miro = result["mirofish"]
        summary_lines.append(f"- Simulation ID: `{miro['simulation_id']}`")
        summary_lines.append(f"- Simulation summary: `{miro['summary']['summary_path']}`")
        summary_lines.append(f"- Run status: `{miro['run_state'].get('runner_status')}`")
        summary_lines.append(f"- Total actions: {miro['run_state'].get('total_actions_count')}")
    summary_path = run_dir / "run_summary.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    result["summary_path"] = str(summary_path)
    return result


def parse_markdown_value(markdown_text: str, label: str) -> str:
    prefix = f"- {label}:"
    for line in markdown_text.splitlines():
        text = line.strip()
        if text.startswith(prefix):
            return text[len(prefix):].strip().strip("`")
    return ""


def find_latest_run(topic_id: str = "") -> Optional[Path]:
    runs_root = DATA_DIR / "runs"
    if not runs_root.exists():
        return None
    candidates: List[Path] = []
    topic_dirs = [runs_root / topic_id] if topic_id else [p for p in runs_root.iterdir() if p.is_dir()]
    for topic_dir in topic_dirs:
        if not topic_dir.exists() or not topic_dir.is_dir():
            continue
        for run_dir in topic_dir.iterdir():
            if run_dir.is_dir():
                candidates.append(run_dir)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def load_run_snapshot(run_dir: Path) -> Dict[str, Any]:
    snapshots = sorted(run_dir.glob("*_snapshot.json"))
    if not snapshots:
        return {}
    return load_json_file(snapshots[-1])


def load_run_summary_markdown(run_dir: Path) -> str:
    summary_path = run_dir / "run_summary.md"
    if not summary_path.exists():
        return ""
    return summary_path.read_text(encoding="utf-8", errors="ignore")


def topic_from_path(run_dir: Path) -> str:
    if run_dir.parent.name == "runs":
        return ""
    return run_dir.parent.name


def build_console_payload(run_dir: Path, mirofish_root: Path) -> Dict[str, Any]:
    snapshot = load_run_snapshot(run_dir)
    summary_markdown = load_run_summary_markdown(run_dir)
    primary_market = (snapshot.get("markets") or [{}])[0]
    simulation_id = parse_markdown_value(summary_markdown, "Simulation ID")
    simulation_entry = None
    if simulation_id:
        for entry in iter_simulation_entries(mirofish_root, include_actions=True):
            if entry.get("simulation_id") == simulation_id:
                simulation_entry = entry
                break
    feed_count = len((snapshot.get("news") or {}).get("items") or [])
    theme_rows = (snapshot.get("news") or {}).get("themes") or []
    top_theme = theme_rows[0]["theme"] if theme_rows else "n/a"
    top_theme_count = theme_rows[0]["count"] if theme_rows else 0
    risk_rows = (snapshot.get("context") or {}).get("riskRows") or []
    risk_summary = ", ".join(
        f"{row.get('region', 'n/a')} {row.get('combinedScore', 'n/a')}"
        for row in risk_rows[:4]
    ) or "n/a"
    modules = snapshot.get("headless_modules") or []
    run_status = "seed-only"
    total_actions = 0
    top_agents: List[str] = []
    counterfactual_note = ""
    if simulation_entry:
        run_status = simulation_entry.get("status") or "unknown"
        total_actions = int(simulation_entry.get("twitter_actions") or 0) + int(simulation_entry.get("reddit_actions") or 0)
        top_agents_payload = parse_action_log(Path(simulation_entry["artifact_paths"]["twitter_log"])).get("top_agents", [])
        top_agents = [f"{name} ({count})" for name, count in top_agents_payload[:3]]
        cf = simulation_entry.get("counterfactual") or {}
        if cf.get("enabled"):
            counterfactual_note = f"branch of {cf.get('base_simulation_id') or 'unknown'} at round {cf.get('injection_round') or 'n/a'}"
    return {
        "topic_id": topic_from_path(run_dir),
        "run_dir": str(run_dir),
        "generated_at": snapshot.get("generated_at") or "n/a",
        "topic": snapshot.get("topic") or "n/a",
        "market_question": primary_market.get("question") or "n/a",
        "market_bid": pct(primary_market.get("bestBid")),
        "market_ask": pct(primary_market.get("bestAsk")),
        "market_deadline": short_dt(primary_market.get("endDate")),
        "market_url": primary_market.get("url") or "n/a",
        "feed_count": feed_count,
        "top_theme": top_theme,
        "top_theme_count": top_theme_count,
        "risk_summary": risk_summary,
        "modules": modules,
        "simulation_id": simulation_id or "n/a",
        "run_status": run_status,
        "total_actions": total_actions,
        "top_agents": top_agents,
        "counterfactual_note": counterfactual_note,
    }


def render_ascii_dashboard(payload: Dict[str, Any], width: int) -> str:
    header_lines = [
        format_kv("topic_id", payload.get("topic_id"), width - 4),
        format_kv("topic", payload.get("topic"), width - 4),
        format_kv("generated_at", payload.get("generated_at"), width - 4),
        format_kv("run_dir", payload.get("run_dir"), width - 4),
    ]
    market_lines = [
        format_kv("market", payload.get("market_question"), width - 4),
        format_kv("bid -> ask", f"{payload.get('market_bid')} -> {payload.get('market_ask')}", width - 4),
        format_kv("deadline", payload.get("market_deadline"), width - 4),
        format_kv("url", payload.get("market_url"), width - 4),
    ]
    signal_lines = [
        format_kv("rss_headlines", payload.get("feed_count"), width - 4),
        format_kv("top_theme", f"{payload.get('top_theme')} ({payload.get('top_theme_count')})", width - 4),
        format_kv("risk", payload.get("risk_summary"), width - 4),
        format_kv("modules", ", ".join(payload.get("modules") or []), width - 4),
    ]
    run_lines = [
        format_kv("simulation_id", payload.get("simulation_id"), width - 4),
        format_kv("status", payload.get("run_status"), width - 4),
        format_kv("total_actions", payload.get("total_actions"), width - 4),
        format_kv("top_agents", ", ".join(payload.get("top_agents") or ["n/a"]), width - 4),
    ]
    if payload.get("counterfactual_note"):
        run_lines.append(format_kv("counterfactual", payload.get("counterfactual_note"), width - 4))
    return "\n".join(
        [
            ascii_box("PREDIHERMES CONSOLE", header_lines, width=width),
            ascii_box("MARKET BOARD", market_lines, width=width),
            ascii_box("OSINT SIGNALS", signal_lines, width=width),
            ascii_box("SIMULATION", run_lines, width=width),
        ]
    )


def cmd_dashboard(args: argparse.Namespace) -> int:
    topic_id = args.topic_id or args.topic_id_pos or ""
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else find_latest_run(topic_id)
    if not run_dir or not run_dir.exists():
        raise PipelineError("No run artifacts found. Run 'run-topic' or 'run-tracked' first.")
    payload = build_console_payload(run_dir, resolve_mirofish_root(args.mirofish_root))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_ascii_dashboard(payload, width=args.width))
    return 0


def cmd_command_catalog(args: argparse.Namespace) -> int:
    items = [
        "health: check WorldOSINT and MiroFish availability",
        "list-worldosint-modules: discover available WorldOSINT modules",
        "track-topic: persist a reusable topic profile",
        "update-topic: modular edits (modules, params, rounds, platform)",
        "plan-tracked <topic_id>: validate feed quality and auto/manual simulation plan",
        "run-tracked <topic_id> [--simulate]: execute latest pipeline path",
        "lookup-sim --query/--actor: resolve base + branch runs from local artifacts",
        "dashboard [--topic-id]: show ASCII run metrics in Hermes CLI",
    ]
    prompts = [
        "Use PrediHermes list-worldosint-modules and suggest modules for maritime conflict monitoring.",
        "Use PrediHermes plan-tracked iran-conflict with budget 1.2 USD and confirm feed quality.",
        "Use PrediHermes dashboard for iran-conflict and summarize risk drift.",
        "Use PrediHermes lookup-sim for actor Shadow Hormuz and compare to base.",
        "Use PrediHermes update-topic to add military_naval and set max rounds to 36.",
    ]
    if args.json:
        print(json.dumps({"commands": items, "example_prompts": prompts}, ensure_ascii=False, indent=2))
        return 0
    width = args.width
    lines = [format_kv(f"{index + 1}", item, width - 4) for index, item in enumerate(items)]
    prompt_lines = [format_kv(f"prompt{index + 1}", prompt, width - 4) for index, prompt in enumerate(prompts)]
    print("\n".join([ascii_box("COMMAND CATALOG", lines, width=width), ascii_box("HERMES ASK EXAMPLES", prompt_lines, width=width)]))
    return 0


def cmd_update_topic(args: argparse.Namespace) -> int:
    state = load_state()
    topic_record = state.get("topics", {}).get(args.topic_id)
    if not topic_record:
        raise PipelineError(f"Tracked topic '{args.topic_id}' does not exist")

    modules = normalize_headless_modules(topic_record.get("headless_modules"))
    set_modules = (args.set_headless_module or []) + (args.set_module or [])
    add_modules = (args.add_headless_module or []) + (args.add_module or [])
    remove_modules = (args.remove_headless_module or []) + (args.remove_module or [])
    if set_modules:
        modules = normalize_headless_modules(set_modules)
    for module in add_modules:
        if module not in modules:
            modules.append(module)
    if remove_modules:
        remove_set = set(remove_modules)
        modules = [name for name in modules if name not in remove_set]
        if not modules:
            raise PipelineError("At least one headless module must remain after removal")
    topic_record["headless_modules"] = modules

    module_params = normalize_module_params(topic_record.get("module_params"))
    if args.set_module_param:
        parsed = parse_module_param_args(args.set_module_param)
        for module_name, payload in parsed.items():
            module_params.setdefault(module_name, {}).update(payload)
    for raw in args.remove_module_param:
        text = str(raw).strip()
        if not text:
            continue
        if "." in text:
            module_name, key = text.split(".", 1)
            if module_name in module_params and key in module_params[module_name]:
                module_params[module_name].pop(key, None)
                if not module_params[module_name]:
                    module_params.pop(module_name, None)
        else:
            module_params.pop(text, None)
    topic_record["module_params"] = module_params

    if args.set_platform:
        topic_record["platform"] = args.set_platform
    if args.set_max_rounds is not None:
        topic_record["max_rounds"] = int(args.set_max_rounds)
    if args.set_parallel_profile_count is not None:
        topic_record["parallel_profile_count"] = int(args.set_parallel_profile_count)
    if args.set_simulation_mode:
        topic_record["simulation_mode"] = args.set_simulation_mode
    if args.set_budget_usd is not None:
        topic_record["budget_usd"] = float(args.set_budget_usd)
    if args.set_target_agents is not None:
        topic_record["target_agents"] = int(args.set_target_agents)
    if args.set_worldosint_base_url:
        topic_record["worldosint_base_url"] = args.set_worldosint_base_url
    if args.set_mirofish_base_url:
        topic_record["mirofish_base_url"] = args.set_mirofish_base_url
    if args.set_mirofish_root:
        topic_record["mirofish_root"] = args.set_mirofish_root

    topic_record["updated_at"] = iso_now()
    save_state(state)
    print(json.dumps(topic_record, ensure_ascii=False, indent=2))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    mirofish_root = resolve_mirofish_root(args.mirofish_root)
    payload = {
        "worldosint": check_worldosint_service(args.worldosint_base_url),
        "mirofish": check_service(args.mirofish_base_url, "/health"),
        "state_path": str(STATE_PATH),
        "state_exists": STATE_PATH.exists(),
        "mirofish_root": str(mirofish_root),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["worldosint"]["ok"] else 1


def cmd_track_topic(args: argparse.Namespace) -> int:
    state = load_state()
    topic_id = args.topic_id or slugify(args.topic)
    topic_record = {
        "topic_id": topic_id,
        "topic": args.topic,
        "market_query": args.market_query or args.topic,
        "keywords": args.keyword or tokenize_terms(args.topic, args.market_query or args.topic),
        "region_codes": args.region_code or [],
        "theater_regions": args.theater_region or THEATER_DEFAULTS,
        "headless_modules": normalize_headless_modules(args.headless_module),
        "module_params": parse_module_param_args(args.module_param),
        "days": args.days,
        "max_deadline_days": args.max_deadline_days,
        "worldosint_base_url": args.worldosint_base_url,
        "mirofish_base_url": args.mirofish_base_url,
        "mirofish_root": args.mirofish_root,
        "platform": args.platform,
        "max_rounds": args.max_rounds,
        "simulation_mode": args.simulation_mode,
        "budget_usd": args.budget_usd,
        "target_agents": args.target_agents,
        "use_llm_for_profiles": bool(args.use_llm_for_profiles),
        "parallel_profile_count": args.parallel_profile_count,
        "enable_graph_memory_update": bool(args.enable_graph_memory_update),
        "created_at": iso_now(),
        "updated_at": iso_now(),
    }
    state.setdefault("topics", {})[topic_id] = topic_record
    save_state(state)
    print(json.dumps(topic_record, ensure_ascii=False, indent=2))
    return 0


def cmd_list_topics(_: argparse.Namespace) -> int:
    state = load_state()
    print(json.dumps(state.get("topics", {}), ensure_ascii=False, indent=2))
    return 0


def cmd_untrack_topic(args: argparse.Namespace) -> int:
    state = load_state()
    removed = state.get("topics", {}).pop(args.topic_id, None)
    save_state(state)
    if not removed:
        raise PipelineError(f"Tracked topic '{args.topic_id}' does not exist")
    print(json.dumps({"removed": args.topic_id}, ensure_ascii=False, indent=2))
    return 0


def topic_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "topic_id": args.topic_id or slugify(args.topic),
        "topic": args.topic,
        "market_query": args.market_query or args.topic,
        "keywords": args.keyword or tokenize_terms(args.topic, args.market_query or args.topic),
        "region_codes": args.region_code or [],
        "theater_regions": args.theater_region or THEATER_DEFAULTS,
        "headless_modules": normalize_headless_modules(args.headless_module),
        "module_params": parse_module_param_args(args.module_param),
        "days": args.days,
        "max_deadline_days": args.max_deadline_days,
        "worldosint_base_url": args.worldosint_base_url,
        "mirofish_base_url": args.mirofish_base_url,
        "mirofish_root": args.mirofish_root,
        "platform": args.platform,
        "max_rounds": args.max_rounds,
        "simulation_mode": args.simulation_mode,
        "budget_usd": args.budget_usd,
        "target_agents": args.target_agents,
        "use_llm_for_profiles": bool(args.use_llm_for_profiles),
        "parallel_profile_count": args.parallel_profile_count,
        "enable_graph_memory_update": bool(args.enable_graph_memory_update),
    }


def runtime_overrides_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "simulation_mode": getattr(args, "simulation_mode", None),
        "budget_usd": getattr(args, "budget_usd", None),
        "target_rounds": getattr(args, "target_rounds", None),
        "target_profile_count": getattr(args, "target_profile_count", None),
        "target_agents": getattr(args, "target_agents", None),
        "require_feed_confirmation": bool(getattr(args, "require_feed_confirmation", False)),
    }


def cmd_run_topic(args: argparse.Namespace) -> int:
    config = topic_from_args(args)
    result = run_topic(
        config,
        simulate=args.simulate,
        generate_report=args.generate_report,
        runtime_overrides=runtime_overrides_from_args(args),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_run_tracked(args: argparse.Namespace) -> int:
    state = load_state()
    config = state.get("topics", {}).get(args.topic_id)
    if not config:
        raise PipelineError(f"Tracked topic '{args.topic_id}' does not exist")
    result = run_topic(
        config,
        simulate=args.simulate,
        generate_report=args.generate_report,
        runtime_overrides=runtime_overrides_from_args(args),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_plan_tracked(args: argparse.Namespace) -> int:
    state = load_state()
    config = state.get("topics", {}).get(args.topic_id)
    if not config:
        raise PipelineError(f"Tracked topic '{args.topic_id}' does not exist")
    result = run_topic(
        config,
        simulate=False,
        generate_report=False,
        runtime_overrides=runtime_overrides_from_args(args),
    )
    output = {
        "topic_id": result.get("topic_id"),
        "topic": result.get("topic"),
        "run_dir": result.get("run_dir"),
        "feed_quality": result.get("feed_quality"),
        "simulation_plan": result.get("simulation_plan"),
        "primary_market": result.get("primary_market"),
        "summary_path": result.get("summary_path"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_lookup_sim(args: argparse.Namespace) -> int:
    mirofish_root = resolve_mirofish_root(args.mirofish_root)
    query_tokens = tokenize_terms(args.query) if args.query else []
    actor_query = args.actor or ""
    simulation_id_filter = normalize_lookup_text(args.simulation_id)
    base_filter = normalize_lookup_text(args.base_simulation_id)

    matches: List[Dict[str, Any]] = []
    for entry in iter_simulation_entries(mirofish_root, include_actions=args.include_actions):
        entry_id = normalize_lookup_text(entry.get("simulation_id"))
        base_simulation_id = normalize_lookup_text((entry.get("counterfactual") or {}).get("base_simulation_id"))

        if simulation_id_filter and simulation_id_filter not in entry_id:
            continue
        if base_filter and base_filter != base_simulation_id:
            continue
        if args.counterfactual_only and not (entry.get("counterfactual") or {}).get("enabled"):
            continue

        matching_actors = select_matching_actors(entry, actor_query) if actor_query else []
        if actor_query and not matching_actors:
            continue

        if query_tokens:
            score = score_entry_match(entry, query_tokens)
            if score <= 0:
                continue
        else:
            score = 1

        entry_copy = dict(entry)
        entry_copy["matching_actors"] = matching_actors
        entry_copy["match_score"] = score
        matches.append(entry_copy)

    matches.sort(
        key=lambda entry: (
            entry.get("match_score", 0),
            normalize_lookup_text(entry.get("updated_at")),
            entry.get("simulation_id", ""),
        ),
        reverse=True,
    )

    output = {
        "mirofish_root": str(mirofish_root),
        "filters": {
            "query": args.query,
            "simulation_id": args.simulation_id,
            "base_simulation_id": args.base_simulation_id,
            "actor": args.actor,
            "counterfactual_only": bool(args.counterfactual_only),
        },
        "matches": matches[: args.limit],
        "total_matches": len(matches),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_list_worldosint_modules(args: argparse.Namespace) -> int:
    payload = fetch_worldosint_modules(args.worldosint_base_url)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    width = args.width
    module_rows = payload.get("modules") or []
    lines: List[str] = []
    for index, row in enumerate(module_rows):
        lines.append(
            format_kv(
                str(index + 1),
                f"{row.get('name')} - {row.get('description') or 'no description'}",
                width - 4,
            )
        )
    if not lines:
        lines = ["No modules returned from WorldOSINT list endpoint."]
    header = [
        format_kv("base", args.worldosint_base_url, width - 4),
        format_kv("count", payload.get("count"), width - 4),
        format_kv("latency_ms", payload.get("latency_ms"), width - 4),
    ]
    print("\n".join([ascii_box("WORLDOSINT MODULES", header, width=width), ascii_box("MODULE INDEX", lines, width=width)]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track geopolitical topics and drive WorldOSINT + Polymarket + MiroFish runs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common_defaults = {
        "worldosint_base_url": DEFAULT_WORLDOSINT_BASE,
        "mirofish_base_url": DEFAULT_MIROFISH_BASE,
        "mirofish_root": str(DEFAULT_MIROFISH_ROOT),
        "days": DEFAULT_DAYS,
        "max_deadline_days": DEFAULT_MAX_DEADLINE_DAYS,
        "platform": DEFAULT_PLATFORM,
        "max_rounds": DEFAULT_MAX_ROUNDS,
        "parallel_profile_count": DEFAULT_PARALLEL_PROFILE_COUNT,
        "simulation_mode": DEFAULT_SIMULATION_MODE,
        "budget_usd": DEFAULT_BUDGET_USD,
        "target_agents": 0,
    }

    def add_topic_config_args(target: argparse.ArgumentParser) -> None:
        target.add_argument("--market-query", default="")
        target.add_argument("--keyword", action="append", default=[])
        target.add_argument("--region-code", action="append", default=[])
        target.add_argument("--theater-region", action="append", default=[])
        target.add_argument("--headless-module", action="append", default=[])
        target.add_argument("--module-param", action="append", default=[])
        for key, value in common_defaults.items():
            target.add_argument(f"--{key.replace('_', '-')}", default=value, type=type(value) if not isinstance(value, str) else str)
        target.add_argument("--use-llm-for-profiles", action="store_true")
        target.add_argument("--enable-graph-memory-update", action="store_true")

    health = subparsers.add_parser("health", help="Check WorldOSINT and MiroFish availability")
    health.add_argument("--worldosint-base-url", default=DEFAULT_WORLDOSINT_BASE)
    health.add_argument("--mirofish-base-url", default=DEFAULT_MIROFISH_BASE)
    health.add_argument("--mirofish-root", default=str(DEFAULT_MIROFISH_ROOT))
    health.set_defaults(func=cmd_health)

    track = subparsers.add_parser("track-topic", help="Persist a tracked topic configuration")
    track.add_argument("--topic-id", default="")
    track.add_argument("--topic", required=True)
    add_topic_config_args(track)
    track.set_defaults(func=cmd_track_topic)

    list_topics = subparsers.add_parser("list-topics", help="Show tracked topics")
    list_topics.set_defaults(func=cmd_list_topics)

    untrack = subparsers.add_parser("untrack-topic", help="Remove a tracked topic")
    untrack.add_argument("topic_id")
    untrack.set_defaults(func=cmd_untrack_topic)

    update_topic = subparsers.add_parser("update-topic", help="Modular updates for a tracked topic profile")
    update_topic.add_argument("topic_id")
    update_topic.add_argument("--set-headless-module", action="append", default=[])
    update_topic.add_argument("--add-headless-module", action="append", default=[])
    update_topic.add_argument("--remove-headless-module", action="append", default=[])
    update_topic.add_argument("--set-module", action="append", default=[])
    update_topic.add_argument("--add-module", action="append", default=[])
    update_topic.add_argument("--remove-module", action="append", default=[])
    update_topic.add_argument("--set-module-param", action="append", default=[])
    update_topic.add_argument("--remove-module-param", action="append", default=[])
    update_topic.add_argument("--set-platform", choices=["twitter", "reddit", "parallel"])
    update_topic.add_argument("--set-max-rounds", type=int)
    update_topic.add_argument("--set-parallel-profile-count", type=int)
    update_topic.add_argument("--set-simulation-mode", choices=["auto", "manual"])
    update_topic.add_argument("--set-budget-usd", type=float)
    update_topic.add_argument("--set-target-agents", type=int)
    update_topic.add_argument("--set-worldosint-base-url", default="")
    update_topic.add_argument("--set-mirofish-base-url", default="")
    update_topic.add_argument("--set-mirofish-root", default="")
    update_topic.set_defaults(func=cmd_update_topic)

    def add_run_args(run_parser: argparse.ArgumentParser, tracked: bool = False) -> None:
        if not tracked:
            run_parser.add_argument("--topic-id", default="")
            run_parser.add_argument("--topic", required=True)
            add_topic_config_args(run_parser)
        else:
            run_parser.add_argument("topic_id")
            run_parser.add_argument("--simulation-mode", choices=["auto", "manual"], default=None)
            run_parser.add_argument("--budget-usd", type=float, default=None)
            run_parser.add_argument("--target-agents", type=int, default=None)
        run_parser.add_argument("--target-rounds", type=int, default=None)
        run_parser.add_argument("--target-profile-count", type=int, default=None)
        run_parser.add_argument("--require-feed-confirmation", action="store_true")
        run_parser.add_argument("--simulate", action="store_true")
        run_parser.add_argument("--generate-report", action="store_true")

    run_topic_parser = subparsers.add_parser("run-topic", help="Run an ad hoc topic through the pipeline")
    add_run_args(run_topic_parser, tracked=False)
    run_topic_parser.set_defaults(func=cmd_run_topic)

    run_tracked_parser = subparsers.add_parser("run-tracked", help="Run a saved topic through the pipeline")
    add_run_args(run_tracked_parser, tracked=True)
    run_tracked_parser.set_defaults(func=cmd_run_tracked)

    plan_tracked_parser = subparsers.add_parser(
        "plan-tracked",
        help="Collect current feeds/market and return feed-quality plus auto/manual simulation plan without running simulation",
    )
    plan_tracked_parser.add_argument("topic_id")
    plan_tracked_parser.add_argument("--simulation-mode", choices=["auto", "manual"], default=None)
    plan_tracked_parser.add_argument("--budget-usd", type=float, default=None)
    plan_tracked_parser.add_argument("--target-rounds", type=int, default=None)
    plan_tracked_parser.add_argument("--target-profile-count", type=int, default=None)
    plan_tracked_parser.add_argument("--target-agents", type=int, default=None)
    plan_tracked_parser.set_defaults(func=cmd_plan_tracked)

    lookup_sim = subparsers.add_parser(
        "lookup-sim",
        help="Resolve MiroFish simulations and injected actors from local artifacts instead of Hermes recall",
    )
    lookup_sim.add_argument("--query", default="")
    lookup_sim.add_argument("--simulation-id", default="")
    lookup_sim.add_argument("--base-simulation-id", default="")
    lookup_sim.add_argument("--actor", default="")
    lookup_sim.add_argument("--mirofish-root", default=str(DEFAULT_MIROFISH_ROOT))
    lookup_sim.add_argument("--limit", type=int, default=10)
    lookup_sim.add_argument("--counterfactual-only", action="store_true")
    lookup_sim.add_argument("--include-actions", action="store_true")
    lookup_sim.set_defaults(func=cmd_lookup_sim)

    list_modules = subparsers.add_parser(
        "list-worldosint-modules",
        help="List available WorldOSINT headless modules for modular configuration",
    )
    list_modules.add_argument("--worldosint-base-url", default=DEFAULT_WORLDOSINT_BASE)
    list_modules.add_argument("--width", type=int, default=DEFAULT_CONSOLE_WIDTH)
    list_modules.add_argument("--json", action="store_true")
    list_modules.set_defaults(func=cmd_list_worldosint_modules)

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Render an ASCII dashboard from latest PrediHermes run artifacts",
    )
    dashboard.add_argument("topic_id_pos", nargs="?", default="")
    dashboard.add_argument("--topic-id", default="")
    dashboard.add_argument("--run-dir", default="")
    dashboard.add_argument("--mirofish-root", default=str(DEFAULT_MIROFISH_ROOT))
    dashboard.add_argument("--width", type=int, default=DEFAULT_CONSOLE_WIDTH)
    dashboard.add_argument("--json", action="store_true")
    dashboard.set_defaults(func=cmd_dashboard)

    command_catalog = subparsers.add_parser(
        "command-catalog",
        help="Show PrediHermes command awareness and Hermes ask patterns",
    )
    command_catalog.add_argument("--width", type=int, default=DEFAULT_CONSOLE_WIDTH)
    command_catalog.add_argument("--json", action="store_true")
    command_catalog.set_defaults(func=cmd_command_catalog)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except PipelineError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    except HTTP_ERROR as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        print(json.dumps({"error": str(exc), "body": body}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
