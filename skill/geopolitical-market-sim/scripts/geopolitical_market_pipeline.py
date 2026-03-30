#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import json
import math
import mimetypes
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

def resolve_pipeline_root(script_path: Path) -> Path:
    candidates = [script_path.parent, script_path.parent.parent]
    for candidate in candidates:
        if (candidate / "tools" / "predihermes" / "review.py").exists():
            return candidate
    return script_path.parent


def resolve_mirofish_source_root(preferred: Optional[str] = None) -> Path:
    candidates: List[Path] = []
    if preferred:
        candidates.append(Path(preferred).expanduser())
    env_root = os.getenv("MIROFISH_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.extend(
        [
            Path.cwd(),
            Path.home() / "Downloads" / "MiroFish-main",
            Path.home() / "MiroFish-main",
            Path("/Users/native/Downloads/MiroFish-main"),
        ]
    )
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "backend" / "app").exists():
            return resolved
    return resolve_pipeline_root(Path(__file__).resolve())


PIPELINE_ROOT = resolve_pipeline_root(Path(__file__).resolve())
MIROFISH_SOURCE_ROOT = resolve_mirofish_source_root(str(PIPELINE_ROOT))
for import_root in (PIPELINE_ROOT, MIROFISH_SOURCE_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def prefer_local_venv_python(root: Path) -> None:
    root_candidates: List[Path] = []
    env_root = os.getenv("MIROFISH_ROOT")
    if env_root:
        root_candidates.append(Path(env_root).expanduser())
    root_candidates.extend(
        [
            Path.cwd(),
            Path.home() / "Downloads" / "MiroFish-main",
            Path.home() / "MiroFish-main",
            Path("/Users/native/Downloads/MiroFish-main"),
            root,
        ]
    )

    seen: set[Path] = set()
    for candidate_root in root_candidates:
        resolved_root = candidate_root.expanduser().resolve()
        if resolved_root in seen:
            continue
        seen.add(resolved_root)
        candidates = [
            resolved_root / ".venv" / "bin" / "python3",
            resolved_root / ".venv" / "bin" / "python",
            resolved_root / "backend" / ".venv" / "bin" / "python3",
            resolved_root / "backend" / ".venv" / "bin" / "python",
        ]
        for venv_python in candidates:
            if not venv_python.exists():
                continue
            if Path(sys.executable).resolve() == venv_python.resolve():
                return
            os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])


prefer_local_venv_python(MIROFISH_SOURCE_ROOT)

from tools.predihermes.review import compile_artifacts, compile_run_artifact
from backend.app.services.zep_entity_reader import ZepEntityReader
from backend.app.services.oasis_profile_generator import OasisProfileGenerator
from backend.app.services.entity_quality import assess_entity_candidate

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
DEFAULT_MIROFISH_ROOT = Path(os.getenv("MIROFISH_ROOT", str(MIROFISH_SOURCE_ROOT))).expanduser()
DEFAULT_MAX_ROUNDS = 24
DEFAULT_PLATFORM = "parallel"
DEFAULT_DAYS = 7
DEFAULT_MAX_DEADLINE_DAYS = 31
DEFAULT_PARALLEL_PROFILE_COUNT = 6
DEFAULT_HEADLESS_MODULES = [
    "news_rss",
    "intelligence_risk_scores",
    "military_usni",
    "intelligence_findings",
    "polymarket_intel",
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
    "AP News",
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
    "News",
    "Trading Odds",
    "Predictions",
}

CAPITALIZED_PHRASE_RE = re.compile(r"\b(?:[A-Z]{2,6}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")

REGION_CODE_HINTS = {
    "IR": ["iran", "tehran", "islamic republic"],
    "IL": ["israel", "jerusalem", "idf"],
    "SA": ["saudi", "saudi arabia", "riyadh"],
    "US": ["united states", "us", "u.s.", "washington"],
}

SHORT_MATCH_ALLOWLIST = {"idf", "iaea", "irgc", "jcpoa"}
MATCH_TERM_STOPWORDS = {
    "after", "before", "between", "calendar", "cannot", "consensus", "credible",
    "creation", "date", "damage", "defined", "including", "land", "listed",
    "market", "otherwise", "purposes", "qualify", "qualifying", "regardless",
    "reporting", "resolution", "resolve", "source", "state", "territory", "that",
    "the", "their", "there", "these", "third", "this", "time", "under", "use",
    "uses", "what", "when", "whether", "which", "will", "with", "yes", "no",
}

MONTH_NAME_TO_NUM = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

TEMPORAL_MONTH_DAY_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s*[-_/]?\s*(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b",
    re.IGNORECASE,
)
TEMPORAL_MONTH_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\b(?:\s+(20\d{2}))?",
    re.IGNORECASE,
)
TEMPORAL_QUARTER_RE = re.compile(r"\bq([1-4])\s*(20\d{2})\b", re.IGNORECASE)
TEMPORAL_YEAR_RE = re.compile(r"\b(20\d{2})\b")


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
    changed = False
    topics = data.get("topics")
    if isinstance(topics, dict):
        for record in topics.values():
            if not isinstance(record, dict):
                continue
            resolved_root = resolve_mirofish_root(record.get("mirofish_root") or DEFAULT_MIROFISH_ROOT)
            resolved_root_text = str(resolved_root)
            if record.get("mirofish_root") != resolved_root_text:
                record["mirofish_root"] = resolved_root_text
                changed = True
    if changed:
        save_state(data)
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


def load_mirofish_env(mirofish_root: Path) -> Dict[str, str]:
    env_path = mirofish_root / ".env"
    values: Dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def load_profile_overrides_file(path_value: Any) -> Dict[str, Any]:
    path_text = str(path_value or "").strip()
    if not path_text:
        return {}
    path = Path(path_text).expanduser()
    if not path.exists():
        raise PipelineError(f"Profile overrides file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Profile overrides file is not valid JSON: {path} ({exc})") from exc
    if not isinstance(payload, (dict, list)):
        raise PipelineError(f"Profile overrides file must contain a JSON object or list: {path}")
    return {"path": str(path), "payload": payload}


def model_list_url(base_url: str) -> str:
    cleaned = (base_url or "").rstrip("/")
    if cleaned.endswith("/v1"):
        return f"{cleaned}/models"
    return f"{cleaned}/v1/models"


def check_llm_backend(mirofish_root: Path) -> Dict[str, Any]:
    require_requests()
    env_values = load_mirofish_env(mirofish_root)
    base_url = env_values.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL", "")
    model_name = env_values.get("LLM_MODEL_NAME") or os.getenv("LLM_MODEL_NAME", "")
    graph_backend = (env_values.get("GRAPH_BACKEND") or os.getenv("GRAPH_BACKEND") or "auto").strip().lower()
    zep_key_set = bool(env_values.get("ZEP_API_KEY") or os.getenv("ZEP_API_KEY"))
    payload: Dict[str, Any] = {
        "base_url": base_url,
        "model_name": model_name,
        "graph_backend": graph_backend or "auto",
        "zep_key_set": zep_key_set,
        "is_local_base_url": base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"),
        "local_profile": {
            "graph_extraction_mode": env_values.get("LOCAL_GRAPH_EXTRACTION_MODE") or os.getenv("LOCAL_GRAPH_EXTRACTION_MODE") or "fast",
            "simulation_profile": env_values.get("LOCAL_SIMULATION_PROFILE") or os.getenv("LOCAL_SIMULATION_PROFILE") or "lean",
            "max_agents": get_local_sim_setting(mirofish_root, "LOCAL_SIM_MAX_AGENTS", 48),
            "max_rounds": get_local_sim_setting(mirofish_root, "LOCAL_SIM_MAX_ROUNDS", 16),
            "parallel_profile_count": get_local_sim_setting(mirofish_root, "LOCAL_SIM_PARALLEL_PROFILE_COUNT", 3),
            "request_timeout_seconds": get_local_sim_setting(mirofish_root, "LOCAL_LLM_REQUEST_TIMEOUT_SECONDS", 900),
            "max_tokens": get_local_sim_setting(mirofish_root, "LOCAL_LLM_MAX_TOKENS", 192),
        },
    }
    if not base_url:
        payload.update({"ok": False, "error": "LLM_BASE_URL is not configured"})
        return payload
    url = model_list_url(base_url)
    started = time.time()
    try:
        response = requests.get(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}, timeout=(5, 20))
        latency_ms = int((time.time() - started) * 1000)
        response.raise_for_status()
        data = response.json() if response.text else {}
        models = [str(row.get("id") or row.get("name") or "") for row in (data.get("data") or data.get("models") or []) if isinstance(row, dict)]
        payload.update(
            {
                "ok": True,
                "latency_ms": latency_ms,
                "models_url": url,
                "available_models": models,
                "model_available": model_name in models if model_name else False,
            }
        )
        return payload
    except REQUEST_EXCEPTION as exc:
        payload.update(
            {
                "ok": False,
                "latency_ms": int((time.time() - started) * 1000),
                "models_url": url,
                "error": str(exc),
            }
        )
        return payload


def mirofish_uses_local_llm(mirofish_root: Path) -> bool:
    env_values = load_mirofish_env(mirofish_root)
    base_url = (env_values.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL") or "").strip().lower()
    return base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost")


def get_local_sim_setting(mirofish_root: Path, key: str, default: int) -> int:
    env_values = load_mirofish_env(mirofish_root)
    raw = (env_values.get(key) or os.getenv(key) or "").strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


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


def normalize_match_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", str(value or "").lower())


def extract_temporal_markers(*values: Any, end_date: Any = None) -> List[str]:
    markers: set[str] = set()

    def add_month(month_value: int, year_value: Optional[int] = None, day_value: Optional[int] = None) -> None:
        markers.add(f"m:{month_value:02d}")
        if year_value:
            markers.add(f"ym:{year_value:04d}-{month_value:02d}")
            markers.add(f"y:{year_value:04d}")
            quarter = ((month_value - 1) // 3) + 1
            markers.add(f"q:{year_value:04d}-q{quarter}")
        if day_value:
            markers.add(f"md:{month_value:02d}-{day_value:02d}")
            if year_value:
                markers.add(f"ymd:{year_value:04d}-{month_value:02d}-{day_value:02d}")

    if end_date:
        dt = to_date(end_date)
        if dt:
            add_month(dt.month, dt.year, dt.day)

    for value in values:
        text = str(value or "")
        if not text:
            continue
        for match in TEMPORAL_MONTH_DAY_RE.finditer(text):
            month = MONTH_NAME_TO_NUM[match.group(1).lower()]
            day = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else None
            add_month(month, year, day)
        for match in TEMPORAL_QUARTER_RE.finditer(text):
            markers.add(f"q:{int(match.group(2)):04d}-q{int(match.group(1))}")
            markers.add(f"y:{int(match.group(2)):04d}")
        for match in TEMPORAL_MONTH_RE.finditer(text):
            month = MONTH_NAME_TO_NUM[match.group(1).lower()]
            year = int(match.group(2)) if match.group(2) else None
            add_month(month, year, None)
        for match in TEMPORAL_YEAR_RE.finditer(text):
            markers.add(f"y:{int(match.group(1)):04d}")
    return sorted(markers)


def _temporal_datetime_from_text(text: str, fallback_year: Optional[int] = None) -> Optional[datetime]:
    raw = str(text or "")
    if not raw:
        return None
    match = TEMPORAL_MONTH_DAY_RE.search(raw)
    if match:
        month = MONTH_NAME_TO_NUM[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else (fallback_year or now_utc().year)
        return datetime(year, month, day, tzinfo=timezone.utc)
    match = TEMPORAL_MONTH_RE.search(raw)
    if match:
        month = MONTH_NAME_TO_NUM[match.group(1).lower()]
        year = int(match.group(2)) if match.group(2) else (fallback_year or now_utc().year)
        day = calendar.monthrange(year, month)[1]
        return datetime(year, month, day, tzinfo=timezone.utc)
    match = TEMPORAL_QUARTER_RE.search(raw)
    if match:
        quarter = int(match.group(1))
        year = int(match.group(2))
        month = quarter * 3
        day = calendar.monthrange(year, month)[1]
        return datetime(year, month, day, tzinfo=timezone.utc)
    match = TEMPORAL_YEAR_RE.search(raw)
    if match:
        year = int(match.group(1))
        return datetime(year, 12, 31, tzinfo=timezone.utc)
    return None


def resolved_market_date(market: Dict[str, Any]) -> Optional[datetime]:
    fallback = to_date(market.get("endDate"))
    fallback_year = fallback.year if fallback else None
    for field in ("question", "description", "title"):
        resolved = _temporal_datetime_from_text(str(market.get(field) or ""), fallback_year=fallback_year)
        if resolved:
            return resolved
    return fallback


def resolved_market_deadline_label(market: Dict[str, Any]) -> str:
    resolved = resolved_market_date(market)
    if not resolved:
        return "n/a"
    return resolved.astimezone(timezone.utc).strftime("%Y-%m-%d 00:00 UTC")


def temporal_alignment_score(intent_markers: List[str], market_markers: List[str]) -> float:
    if not intent_markers:
        return 0.0
    if not market_markers:
        return -1.0

    weights = {
        "ymd:": 8.0,
        "md:": 6.0,
        "ym:": 4.0,
        "m:": 2.5,
        "q:": 2.0,
        "y:": 1.0,
    }

    def marker_weight(marker: str) -> float:
        for prefix, weight in weights.items():
            if marker.startswith(prefix):
                return weight
        return 1.0

    score = sum(marker_weight(marker) for marker in intent_markers if marker in market_markers)
    families = ("ymd:", "md:", "ym:", "m:", "q:", "y:")
    for family in families:
        expected = [marker for marker in intent_markers if marker.startswith(family)]
        actual = [marker for marker in market_markers if marker.startswith(family)]
        if expected and actual and not (set(expected) & set(actual)):
            score -= max(marker_weight(marker) for marker in expected)
    return score


def canonical_market_anchor(market: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "slug": str(market.get("slug") or ""),
        "question": str(market.get("question") or ""),
        "description": str(market.get("description") or ""),
        "condition_id": str(market.get("conditionId") or ""),
        "end_date": str(market.get("endDate") or ""),
        "resolution_deadline": resolved_market_deadline_label(market),
        "resolution_markers": extract_temporal_markers(
            market.get("question"),
            market.get("description"),
            end_date=market.get("endDate"),
        ),
    }


def build_market_intent(
    *,
    topic: str,
    query: str,
    keywords: List[str],
    region_codes: List[str],
    market_anchor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    anchor = market_anchor or {}
    anchor_question = str(anchor.get("question") or "")
    anchor_description = str(anchor.get("description") or "")
    terms = build_topic_match_terms(
        topic,
        keywords,
        " ".join(part for part in [query, anchor_question, anchor_description] if part),
        region_codes,
    )
    temporal_markers = extract_temporal_markers(topic, query, anchor_question, anchor_description)
    if not temporal_markers and isinstance(anchor.get("resolution_markers"), list):
        temporal_markers = [str(marker) for marker in anchor.get("resolution_markers") if marker]
    return {
        "terms": terms,
        "temporal_markers": temporal_markers,
        "anchor_slug": str(anchor.get("slug") or ""),
        "anchor_condition_id": str(anchor.get("condition_id") or ""),
        "anchor_question": anchor_question,
    }


def build_topic_match_terms(
    topic: str,
    keywords: List[str],
    market_question: str,
    region_codes: List[str],
) -> List[str]:
    terms = set()
    sources = [topic, market_question, *keywords]
    for raw in sources:
        text = normalize_match_text(raw)
        for token in text.split():
            if len(token) >= 3 and token not in MATCH_TERM_STOPWORDS:
                terms.add(token)
        if text.strip() and 1 < len(text.split()) <= 6:
            terms.add(text.strip())
    for code in region_codes:
        for hint in REGION_CODE_HINTS.get(str(code).upper(), []):
            terms.add(hint)
    cleaned_terms = []
    for term in terms:
        normalized = term.strip()
        if not normalized:
            continue
        compact = normalized.replace(" ", "")
        if len(compact) < 4 and compact not in SHORT_MATCH_ALLOWLIST:
            continue
        if compact in MATCH_TERM_STOPWORDS:
            continue
        cleaned_terms.append(normalized)
    return sorted(set(cleaned_terms))


def text_matches_terms(value: Any, terms: List[str]) -> bool:
    haystack = normalize_match_text(value)
    if not haystack:
        return False
    return any(term in haystack for term in terms)


def merge_module_params(
    module_params: Dict[str, Dict[str, Any]],
    *,
    topic: str,
    keywords: List[str],
    primary_market: Dict[str, Any],
    region_codes: List[str],
    days: int,
) -> Dict[str, Dict[str, Any]]:
    merged = {name: dict(payload) for name, payload in module_params.items()}
    if "intelligence_findings" not in merged:
        merged["intelligence_findings"] = {
            "regions": region_codes or ["IR", "IL", "SA", "US"],
            "window_days": days,
        }
    if "polymarket_intel" not in merged:
        merged["polymarket_intel"] = {
            "query": primary_market.get("question") or topic,
            "limit": 100,
        }
    return merged


def compact_trade_notional(row: Dict[str, Any]) -> float:
    candidates = [
        row.get("tradeNotional"),
        row.get("amountUsd"),
        row.get("sizeUsd"),
        row.get("dollar_volume"),
        row.get("volumeUsd"),
        row.get("notional"),
        row.get("size"),
        row.get("amount"),
    ]
    for value in candidates:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    try:
        price = float(row.get("price") or 0.0)
        size = float(row.get("size") or row.get("amount") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if price > 0 and size > 0:
        return round(price * size, 4)
    return 0.0


def curate_intelligence_findings(payload: Dict[str, Any], terms: List[str]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    findings = (data or {}).get("findings") or []
    relevant = []
    for finding in findings:
        haystack = " ".join(
            [
                str(finding.get("title") or ""),
                str(finding.get("summary") or ""),
                json.dumps(finding.get("payload") or {}, ensure_ascii=False),
            ]
        )
        if text_matches_terms(haystack, terms):
            relevant.append(finding)
    summary_counter: Counter[str] = Counter()
    for finding in relevant:
        summary_counter[str(finding.get("priority") or "unknown").lower()] += 1
    curated = {
        "findings": relevant[:12],
        "summary": {
            "critical": summary_counter.get("critical", 0),
            "high": summary_counter.get("high", 0),
            "medium": summary_counter.get("medium", 0),
            "low": summary_counter.get("low", 0),
            "total": len(relevant),
            "raw_total": len(findings),
        },
        "sources": sorted({str(row.get("source") or "") for row in relevant if row.get("source")}),
    }
    return {
        **payload,
        "data": curated,
    }


def curate_polymarket_intel(payload: Dict[str, Any], primary_market: Dict[str, Any], terms: List[str]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    slug = str(primary_market.get("slug") or "")
    question = str(primary_market.get("question") or "").lower()
    condition_id = str(primary_market.get("conditionId") or "")

    def market_match(row: Dict[str, Any]) -> bool:
        row_text = " ".join(
            [
                str(row.get("question") or ""),
                str(row.get("title") or ""),
                str(row.get("slug") or ""),
                str(row.get("description") or ""),
            ]
        )
        if row.get("conditionId") == condition_id or row.get("slug") == slug:
            return True
        return text_matches_terms(row_text, terms)

    def trade_match(row: Dict[str, Any]) -> bool:
        row_text = " ".join(
            [
                str(row.get("title") or ""),
                str(row.get("slug") or ""),
                str(row.get("conditionId") or ""),
            ]
        )
        if row.get("conditionId") == condition_id or row.get("slug") == slug:
            return True
        return text_matches_terms(row_text, terms) or str(row.get("title") or "").lower() == question

    matched_markets = [row for row in (data or {}).get("markets") or [] if isinstance(row, dict) and market_match(row)]
    matched_trades = [row for row in (data or {}).get("trades") or [] if isinstance(row, dict) and trade_match(row)]
    matched_trades.sort(key=compact_trade_notional, reverse=True)
    total_notional = round(sum(compact_trade_notional(row) for row in matched_trades), 2)
    curated = {
        "matched_market_count": len(matched_markets),
        "matched_trade_count": len(matched_trades),
        "matched_trades_notional": total_notional,
        "matched_markets": [
            {
                "question": row.get("question") or row.get("title") or "",
                "slug": row.get("slug") or "",
                "conditionId": row.get("conditionId") or "",
                "endDate": row.get("endDate") or "",
                "outcomePrices": row.get("outcomePrices") or "",
            }
            for row in matched_markets[:6]
        ],
        "matched_trades": [
            {
                "title": row.get("title") or "",
                "slug": row.get("slug") or "",
                "side": row.get("side") or "",
                "outcome": row.get("outcome") or "",
                "price": row.get("price"),
                "tradeNotional": compact_trade_notional(row),
                "timestamp": row.get("timestamp"),
                "transactionHash": row.get("transactionHash") or "",
            }
            for row in matched_trades[:12]
        ],
    }
    return {
        **payload,
        "data": curated,
    }


def curate_extra_modules(
    extra_modules: Dict[str, Any],
    *,
    topic: str,
    keywords: List[str],
    primary_market: Dict[str, Any],
    region_codes: List[str],
) -> Dict[str, Any]:
    terms = build_topic_match_terms(topic, keywords, primary_market.get("question") or "", region_codes)
    curated: Dict[str, Any] = {}
    for module_name, payload in extra_modules.items():
        if module_name == "intelligence_findings":
            curated[module_name] = curate_intelligence_findings(payload, terms)
        elif module_name == "polymarket_intel":
            curated[module_name] = curate_polymarket_intel(payload, primary_market, terms)
        else:
            curated[module_name] = payload
    return curated


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


def is_market_commentary_item(item: Dict[str, Any]) -> bool:
    title = normalize_match_text(item.get("title"))
    source = normalize_match_text(item.get("source"))
    return (
        "polymarket" in title
        or "polymarket" in source
        or ("trading odds" in title and "prediction" in title)
    )


def relevant_news_items(
    items: List[Dict[str, Any]],
    *,
    topic: str,
    keywords: List[str],
    primary_market: Dict[str, Any],
    region_codes: List[str],
) -> List[Dict[str, Any]]:
    terms = build_topic_match_terms(
        topic,
        keywords,
        str(primary_market.get("question") or ""),
        region_codes,
    )
    temporal_markers = extract_temporal_markers(
        topic,
        primary_market.get("question"),
        primary_market.get("description"),
        end_date=primary_market.get("endDate"),
    )
    filtered: List[Dict[str, Any]] = []
    for item in items:
        if is_market_commentary_item(item):
            continue
        haystack = str(item.get("title", ""))
        normalized_haystack = normalize_match_text(haystack)
        match_count = sum(1 for term in terms if term in normalized_haystack)
        score = topic_match_score(haystack, terms) * 10
        score += temporal_alignment_score(temporal_markers, extract_temporal_markers(haystack))
        if match_count == 0 or score < 1.0:
            continue
        item_copy = dict(item)
        item_copy["relevanceScore"] = round(score, 3)
        item_copy["matchCount"] = match_count
        filtered.append(item_copy)
    filtered.sort(
        key=lambda item: (
            float(item.get("relevanceScore") or 0),
            to_date(item.get("pubDateIso")) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return filtered


def fetch_news_snapshot(
    base_url: str,
    topic: str,
    days: int,
    keywords: List[str],
    primary_market: Dict[str, Any],
    region_codes: List[str],
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
    items = dedupe_news(
        relevant_news_items(
            items,
            topic=topic,
            keywords=keywords,
            primary_market=primary_market,
            region_codes=region_codes,
        )
    )
    theme_counts = Counter(classify_theme(item.get("title", "")) for item in items)
    themes = [{"theme": theme, "count": count} for theme, count in theme_counts.most_common(8)]
    actor_terms = build_topic_match_terms(topic, keywords, str(primary_market.get("question") or ""), region_codes)
    actors = extract_candidate_actors(
        [item.get("title", "") for item in items],
        limit=12,
        anchor_terms=actor_terms,
        anchor_text=str(primary_market.get("question") or ""),
    )
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
    if isinstance(end_date, dict):
        dt = resolved_market_date(end_date)
    else:
        dt = to_date(end_date)
    if not dt:
        return 9999.0
    return (dt - now_utc()).total_seconds() / 86400.0


def score_market(market: Dict[str, Any], intent: Dict[str, Any], max_deadline_days: int) -> float:
    text = " ".join(
        str(market.get(field, ""))
        for field in ("question", "description", "title")
    )
    terms = list(intent.get("terms") or [])
    temporal_markers = list(intent.get("temporal_markers") or [])
    match = topic_match_score(text, terms) * 12
    deadline_days = market_deadline_days(market)
    if deadline_days < 0 or deadline_days > max_deadline_days:
        return -1e9
    deadline_bonus = (max_deadline_days - deadline_days) / max(max_deadline_days, 1) * 2
    volume_bonus = math.log10(float(market.get("volumeNum") or 0) + 1)
    liquidity_bonus = math.log10(float(market.get("liquidityNum") or 0) + 1)
    clarity_bonus = 1.0 if str(market.get("question", "")).strip().endswith("?") else 0.0
    market_markers = extract_temporal_markers(text, end_date=market.get("endDate"))
    temporal_bonus = temporal_alignment_score(temporal_markers, market_markers)
    anchor_bonus = 0.0
    if intent.get("anchor_slug") and str(market.get("slug") or "") == intent["anchor_slug"]:
        anchor_bonus += 6.0
    if intent.get("anchor_condition_id") and str(market.get("conditionId") or "") == intent["anchor_condition_id"]:
        anchor_bonus += 6.0
    if intent.get("anchor_question") and normalize_match_text(intent["anchor_question"]) == normalize_match_text(market.get("question")):
        anchor_bonus += 3.0
    return match + deadline_bonus + volume_bonus + liquidity_bonus + clarity_bonus + temporal_bonus + anchor_bonus


def search_markets(query: str, max_deadline_days: int, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = request_json("GET", f"{GAMMA_API}/public-search?q={quote(query)}")
    events = data.get("events", [])
    seen = set()
    candidates: List[Dict[str, Any]] = []
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
            market_copy["score"] = score_market(market_copy, intent, max_deadline_days)
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
        "resolutionDeadline": resolved_market_deadline_label(market),
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


def select_markets(
    query: str,
    max_deadline_days: int,
    *,
    topic: str = "",
    keywords: Optional[List[str]] = None,
    region_codes: Optional[List[str]] = None,
    market_anchor: Optional[Dict[str, Any]] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    intent = build_market_intent(
        topic=topic,
        query=query,
        keywords=keywords or [],
        region_codes=region_codes or [],
        market_anchor=market_anchor,
    )
    candidates = search_markets(query, max_deadline_days, intent)
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
    selected.sort(
        key=lambda market: (
            score_market(market, intent, max_deadline_days),
            -market_deadline_days(market),
        ),
        reverse=True,
    )
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


def extract_candidate_actors(
    texts: List[str],
    *,
    limit: int = 10,
    anchor_terms: Optional[List[str]] = None,
    anchor_text: str = "",
) -> List[Dict[str, Any]]:
    counts: Counter[str] = Counter()
    for text in texts:
        for match in CAPITALIZED_PHRASE_RE.findall(text or ""):
            phrase = match.strip()
            if not phrase or phrase in SOURCE_STOPWORDS:
                continue
            if phrase.lower() in {"yes", "no", "will", "what", "when"}:
                continue
            quality = assess_entity_candidate(
                phrase,
                anchor_terms=anchor_terms,
                anchor_text=anchor_text,
            )
            if not quality.keep:
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
    deadline = str(primary_market.get("resolutionDeadline") or resolved_market_deadline_label(primary_market))
    question = primary_market.get("question", "")
    return (
        f"Forecast whether the Polymarket contract '{question}' resolves YES by {deadline}. "
        f"Use the seed packet to simulate the geopolitical topic '{topic}', actor incentives, escalation pathways, "
        f"diplomatic pathways, and the exact evidence threshold implied by the market wording and description. "
        f"If topic shorthand and contract timing diverge, prioritize the contract wording and deadline. "
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
    lines.append(f"- Resolution deadline: {primary_market.get('resolutionDeadline') or resolved_market_deadline_label(primary_market)}")
    lines.append(f"- Market close timestamp: {short_dt(primary_market['endDate'])}")
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
            lines.append(
                f"| {market['question']} | {pct(market['bestBid'])} | {pct(market['bestAsk'])} | "
                f"{market.get('resolutionDeadline') or resolved_market_deadline_label(market)} |"
            )
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
    lines.append(
        f"Use this packet to simulate whether the primary contract resolves Yes before "
        f"{primary_market.get('resolutionDeadline') or resolved_market_deadline_label(primary_market)}."
    )
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


def build_simulation_brief_markdown(
    topic: str,
    primary_market: Dict[str, Any],
    news: Dict[str, Any],
    context: Dict[str, Any],
    extra_modules: Dict[str, Any],
) -> str:
    description_points = split_description_points(primary_market.get("description", ""))
    finding_rows = (((extra_modules.get("intelligence_findings") or {}).get("data") or {}).get("findings") or [])[:8]
    market_intel = ((extra_modules.get("polymarket_intel") or {}).get("data") or {})
    risk_rows = (context.get("riskRows") or [])[:4]
    actor_rows = (news.get("actors") or [])[:10]
    theme_rows = (news.get("themes") or [])[:6]
    headline_rows = (news.get("items") or [])[:10]

    paragraphs: List[str] = []
    paragraphs.append(
        f"This simulation concerns {topic}. The target contract asks whether '{primary_market.get('question')}' resolves YES by "
        f"{primary_market.get('resolutionDeadline') or resolved_market_deadline_label(primary_market)}."
    )
    if description_points:
        paragraphs.append("Resolution language and contract framing: " + " ".join(description_points[:3]))
    paragraphs.append(
        f"Current market state: best bid {pct(primary_market.get('bestBid'))}, best ask {pct(primary_market.get('bestAsk'))}, liquidity {human_money(primary_market.get('liquidityNum'))}, volume {human_money(primary_market.get('volumeNum'))}."
    )
    if actor_rows:
        actor_text = ", ".join(f"{row['label']} ({row['count']})" for row in actor_rows[:8])
        paragraphs.append(f"Relevant named actors and organizations already present in the evidence: {actor_text}.")
    if theme_rows:
        theme_text = ", ".join(f"{row['theme']} ({row['count']})" for row in theme_rows[:5])
        paragraphs.append(f"Dominant evidence themes: {theme_text}.")
    if risk_rows:
        risk_text = "; ".join(
            f"{row.get('region', 'n/a')} combined risk {row.get('combinedScore', 'n/a')} trend {str(row.get('trend', '')).replace('TREND_DIRECTION_', '')}"
            for row in risk_rows
        )
        paragraphs.append(f"Regional monitoring snapshot: {risk_text}.")
    if finding_rows:
        finding_text = " ".join(
            f"{str(row.get('title') or '').strip()}. {str(row.get('summary') or '').strip()}".strip()
            for row in finding_rows
        )
        paragraphs.append(f"Recent intelligence and OSINT findings: {finding_text}")
    if market_intel.get("matched_trades"):
        trade_rows = market_intel.get("matched_trades") or []
        trade_text = " ".join(
            f"{row.get('side') or 'n/a'} {row.get('outcome') or 'n/a'} at {row.get('price')} for {human_money(row.get('tradeNotional'))}."
            for row in trade_rows[:6]
        )
        paragraphs.append(
            f"Polymarket flow relevant to this contract totals {human_money(market_intel.get('matched_trades_notional') or 0)} across {market_intel.get('matched_trade_count') or 0} matched trades. {trade_text}"
        )
    if headline_rows:
        headline_text = " ".join(
            f"\"{str(row.get('title') or '').strip()}\""
            for row in headline_rows
        )
        paragraphs.append(f"Recent news pulse includes: {headline_text}")
    paragraphs.append(
        "Model concrete actors, incentives, and verification milestones only. Ignore feed labels, metadata, timestamps, and headline fragments. Focus on which observable diplomatic or escalation events would move the contract from likely NO to plausible YES before expiry."
    )
    return "\n\n".join(paragraphs).strip() + "\n"


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


def close_simulation_env(base_url: str, simulation_id: str, *, timeout_seconds: int = 30) -> Dict[str, Any]:
    payload = request_json(
        "POST",
        f"{base_url.rstrip('/')}/api/simulation/close-env",
        json={"simulation_id": simulation_id, "timeout": timeout_seconds},
    )
    return payload.get("data") or {}


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
        "agent_count": len(config.get("agent_configs") or config.get("agents") or []),
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


def write_mirofish_link(run_dir: Path, payload: Dict[str, Any]) -> Path:
    path = run_dir / "mirofish_link.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged = {
        "version": 1,
        "updated_at": iso_now(),
        **existing,
        **payload,
    }
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def persist_topic_market_anchor(topic_id: str, primary_market: Dict[str, Any]) -> None:
    state = load_state()
    topic_record = state.get("topics", {}).get(topic_id)
    if not topic_record:
        return
    topic_record["market_anchor"] = canonical_market_anchor(primary_market)
    topic_record["updated_at"] = iso_now()
    save_state(state)


def run_mirofish_pipeline(
    *,
    topic: str,
    source_path: Path,
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
    profile_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    require_requests()
    if mirofish_uses_local_llm(mirofish_root):
        max_rounds = min(max_rounds, get_local_sim_setting(mirofish_root, "LOCAL_SIM_MAX_ROUNDS", 16))
        parallel_profile_count = min(
            parallel_profile_count,
            get_local_sim_setting(mirofish_root, "LOCAL_SIM_PARALLEL_PROFILE_COUNT", 3),
        )
    requirement = generate_simulation_requirement(topic, primary_market)
    mime_type = mimetypes.guess_type(source_path.name)[0] or "text/markdown"
    with source_path.open("rb") as handle:
        ontology_payload = requests.post(
            f"{mirofish_base_url.rstrip('/')}/api/graph/ontology/generate",
            data={
                "simulation_requirement": requirement,
                "project_name": f"Hermes {topic} {source_path.parent.name}",
            },
            files={"files": (source_path.name, handle, mime_type)},
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
    link_path = write_mirofish_link(
        run_dir,
        {
            "topic": topic,
            "primary_market_question": primary_market.get("question"),
            "mirofish_root": str(mirofish_root),
            "mirofish_base_url": mirofish_base_url,
            "project_id": project_id,
            "graph_id": graph_id,
            "simulation_id": simulation_id,
            "status": "created",
        },
    )

    prepare_payload = request_json(
        "POST",
        f"{mirofish_base_url.rstrip('/')}/api/simulation/prepare",
        json={
            "simulation_id": simulation_id,
            "use_llm_for_profiles": use_llm_for_profiles,
            "parallel_profile_count": parallel_profile_count,
            "profile_overrides": profile_overrides or None,
        },
    )
    prepare_data = prepare_payload.get("data") or {}
    prepare_task_id = prepare_data.get("task_id")
    write_mirofish_link(
        run_dir,
        {
            "simulation_id": simulation_id,
            "prepare_task_id": prepare_task_id,
            "status": "preparing" if prepare_task_id else str(prepare_data.get("status") or "created"),
        },
    )
    if prepare_task_id:
        poll_prepare(mirofish_base_url, simulation_id, prepare_task_id)
    elif prepare_data.get("status") not in {"ready"}:
        raise PipelineError("MiroFish prepare did not return a task_id or ready status")
    write_mirofish_link(
        run_dir,
        {
            "simulation_id": simulation_id,
            "prepare_task_id": prepare_task_id,
            "status": "ready",
        },
    )

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
    write_mirofish_link(
        run_dir,
        {
            "simulation_id": simulation_id,
            "prepare_task_id": prepare_task_id,
            "start_data": start_payload.get("data") or {},
            "status": "running",
            "link_path": str(link_path),
        },
    )
    run_state = poll_run(mirofish_base_url, simulation_id)
    write_mirofish_link(
        run_dir,
        {
            "simulation_id": simulation_id,
            "prepare_task_id": prepare_task_id,
            "start_data": start_payload.get("data") or {},
            "run_state": run_state,
            "status": str(run_state.get("runner_status") or "unknown"),
        },
    )

    report_data: Dict[str, Any] = {}
    if generate_report:
        report_payload = request_json(
            "POST",
            f"{mirofish_base_url.rstrip('/')}/api/report/generate",
            json={"simulation_id": simulation_id},
        )
        report_data = report_payload.get("data") or {}

    summary = summarize_simulation_run(run_dir, mirofish_root, simulation_id, primary_market, topic)
    close_env_result: Dict[str, Any] = {}
    if str(run_state.get("runner_status") or "").lower() == "completed":
        try:
            close_env_result = close_simulation_env(mirofish_base_url, simulation_id)
        except Exception as exc:
            close_env_result = {"success": False, "error": str(exc)}
        write_mirofish_link(
            run_dir,
            {
                "simulation_id": simulation_id,
                "close_env": close_env_result,
            },
        )
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
        "close_env": close_env_result,
    }


def run_topic(config: Dict[str, Any], *, simulate: bool, generate_report: bool) -> Dict[str, Any]:
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
    profile_overrides_file = load_profile_overrides_file(config.get("profile_overrides_path"))
    market_anchor = config.get("market_anchor") if isinstance(config.get("market_anchor"), dict) else {}
    headless_modules = dedupe_strings(
        normalize_headless_modules(config.get("headless_modules"))
        + ["intelligence_findings", "polymarket_intel"]
    )
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

    markets = select_markets(
        market_query,
        max_deadline_days,
        topic=topic,
        keywords=keywords,
        region_codes=region_codes,
        market_anchor=market_anchor,
    )
    if config.get("_persist_market_anchor"):
        persist_topic_market_anchor(topic_id, markets[0])
    module_params = merge_module_params(
        module_params,
        topic=topic,
        keywords=keywords,
        primary_market=markets[0],
        region_codes=region_codes,
        days=days,
    )
    news = {"feeds": [], "items": [], "themes": [], "actors": []}
    if "news_rss" in headless_modules:
        news = fetch_news_snapshot(
            worldosint_base,
            topic,
            days,
            keywords,
            markets[0],
            region_codes,
            module_params.get("news_rss"),
        )
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
    extra_modules = curate_extra_modules(
        extra_modules,
        topic=topic,
        keywords=keywords,
        primary_market=markets[0],
        region_codes=region_codes,
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
    simulation_brief_markdown = build_simulation_brief_markdown(
        topic=topic,
        primary_market=markets[0],
        news=news,
        context=context,
        extra_modules=extra_modules,
    )
    seed_path = run_dir / f"{topic_id}_seed.md"
    simulation_brief_path = run_dir / f"{topic_id}_simulation_brief.md"
    snapshot_path = run_dir / f"{topic_id}_snapshot.json"
    seed_path.write_text(seed_markdown, encoding="utf-8")
    simulation_brief_path.write_text(simulation_brief_markdown, encoding="utf-8")

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
        "market_anchor": canonical_market_anchor(markets[0]),
        "news": news,
        "context": context,
        "extra_modules": extra_modules,
        "seed_path": str(seed_path),
        "simulation_brief_path": str(simulation_brief_path),
        "simulate": simulate,
        "profile_overrides_path": profile_overrides_file.get("path", ""),
    }
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    result: Dict[str, Any] = {
        "topic_id": topic_id,
        "topic": topic,
        "run_dir": str(run_dir),
        "seed_path": str(seed_path),
        "simulation_brief_path": str(simulation_brief_path),
        "snapshot_path": str(snapshot_path),
        "primary_market": markets[0],
        "related_markets": markets[1:],
        "worldosint_status": world_status,
        "mirofish_status": mirofish_status,
    }

    if simulate:
        result["mirofish"] = run_mirofish_pipeline(
            topic=topic,
            source_path=simulation_brief_path,
            primary_market=markets[0],
            mirofish_base_url=mirofish_base,
            mirofish_root=mirofish_root,
            platform=platform,
            max_rounds=max_rounds,
            use_llm_for_profiles=use_llm_for_profiles,
            parallel_profile_count=parallel_profile_count,
            enable_graph_memory_update=enable_graph_memory_update,
            generate_report=generate_report,
            run_dir=run_dir,
            profile_overrides=profile_overrides_file.get("payload") or None,
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
    summary_lines.append(f"- Resolution deadline: {markets[0].get('resolutionDeadline') or resolved_market_deadline_label(markets[0])}")
    summary_lines.append(f"- URL: {markets[0]['url']}")
    summary_lines.append(f"- WorldOSINT modules: {', '.join(headless_modules)}")
    summary_lines.append("")
    summary_lines.append("## Artifacts")
    summary_lines.append("")
    summary_lines.append(f"- Seed packet: `{seed_path}`")
    summary_lines.append(f"- Simulation brief: `{simulation_brief_path}`")
    summary_lines.append(f"- Raw snapshot: `{snapshot_path}`")
    if profile_overrides_file.get("path"):
        summary_lines.append(f"- Profile overrides: `{profile_overrides_file['path']}`")
    if simulate:
        miro = result["mirofish"]
        summary_lines.append(f"- Simulation ID: `{miro['simulation_id']}`")
        summary_lines.append(f"- Simulation summary: `{miro['summary']['summary_path']}`")
        summary_lines.append(f"- Run status: `{miro['run_state'].get('runner_status')}`")
        summary_lines.append(f"- Total actions: {miro['run_state'].get('total_actions_count')}")
    summary_path = run_dir / "run_summary.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    compile_artifacts(data_root=DATA_DIR, mirofish_root=mirofish_root, topic_id=topic_id)
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


def ensure_compiled_run_artifacts(run_dir: Path, mirofish_root: Path) -> Dict[str, Any]:
    decision_path = run_dir / "decision_artifact.json"
    if not decision_path.exists():
        compile_run_artifact(run_dir, mirofish_root)
    artifact = load_json_file(decision_path)
    alerts_path = run_dir / "alerts.json"
    if not alerts_path.exists():
        topic_id = str(artifact.get("topic_id") or topic_from_path(run_dir) or "")
        compile_artifacts(data_root=DATA_DIR, mirofish_root=mirofish_root, topic_id=topic_id)
    return artifact


def build_console_payload(run_dir: Path, mirofish_root: Path) -> Dict[str, Any]:
    artifact = ensure_compiled_run_artifacts(run_dir, mirofish_root)
    snapshot = load_run_snapshot(run_dir)
    alerts_payload = load_json_file(run_dir / "alerts.json")
    evidence_payload = load_json_file(run_dir / "evidence_lineage.json")
    market = artifact.get("market") or {}
    signals = artifact.get("signals") or {}
    forecast = artifact.get("forecast") or {}
    simulation = artifact.get("simulation") or {}
    branch = artifact.get("branch") or {}
    extra_modules = snapshot.get("extra_modules") or {}
    findings = (((extra_modules.get("intelligence_findings") or {}).get("data") or {}).get("findings") or [])
    finding_summary = (((extra_modules.get("intelligence_findings") or {}).get("data") or {}).get("summary") or {})
    market_intel = ((extra_modules.get("polymarket_intel") or {}).get("data") or {})
    risk_rows = (snapshot.get("context") or {}).get("riskRows") or []
    risk_summary = ", ".join(
        f"{row.get('region', 'n/a')} {row.get('combinedScore', 'n/a')}"
        for row in risk_rows[:4]
    ) or "n/a"
    top_theme_rows = signals.get("top_themes") or []
    top_agents = [
        f"{name} ({count})"
        for name, count in (simulation.get("top_agents") or [])[:3]
    ]
    return {
        "topic_id": topic_from_path(run_dir),
        "run_dir": str(run_dir),
        "generated_at": artifact.get("generated_at") or "n/a",
        "topic": artifact.get("topic") or "n/a",
        "market_question": market.get("question") or "n/a",
        "market_bid": market.get("best_bid"),
        "market_ask": market.get("best_ask"),
        "market_deadline": market.get("deadline_display") or "n/a",
        "market_url": market.get("url") or "n/a",
        "market_mid": forecast.get("market_yes_probability"),
        "predicted_yes": forecast.get("predicted_yes_probability"),
        "forecast_call": forecast.get("call") or "n/a",
        "forecast_confidence": forecast.get("confidence"),
        "forecast_thesis": forecast.get("thesis") or "",
        "feed_count": signals.get("headline_count") or 0,
        "top_theme": top_theme_rows[0]["theme"] if top_theme_rows else "n/a",
        "top_theme_count": top_theme_rows[0]["count"] if top_theme_rows else 0,
        "risk_summary": risk_summary,
        "finding_count": len(findings),
        "finding_raw_total": finding_summary.get("raw_total") or 0,
        "market_intel_trades": market_intel.get("matched_trade_count") or 0,
        "market_intel_notional": market_intel.get("matched_trades_notional") or 0,
        "modules": signals.get("module_set") or [],
        "simulation_id": simulation.get("simulation_id") or "n/a",
        "run_status": simulation.get("status") or "seed-only",
        "total_actions": int(simulation.get("lines") or 0),
        "top_agents": top_agents,
        "counterfactual_note": f"branch of {branch.get('base_simulation_id') or 'unknown'} at round {branch.get('injection_round') or 'n/a'}" if branch.get("enabled") else "",
        "drivers": forecast.get("drivers") or [],
        "alerts": alerts_payload.get("alerts") or [],
        "evidence_count": len(evidence_payload.get("evidence") or []),
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
        format_kv("market_mid", pct(payload.get("market_mid")), width - 4),
        format_kv("predicted_yes", pct(payload.get("predicted_yes")), width - 4),
        format_kv("deadline", payload.get("market_deadline"), width - 4),
        format_kv("url", payload.get("market_url"), width - 4),
    ]
    signal_lines = [
        format_kv("rss_headlines", payload.get("feed_count"), width - 4),
        format_kv("top_theme", f"{payload.get('top_theme')} ({payload.get('top_theme_count')})", width - 4),
        format_kv("risk", payload.get("risk_summary"), width - 4),
        format_kv("intel_findings", f"{payload.get('finding_count')} relevant / {payload.get('finding_raw_total')} raw", width - 4),
        format_kv("market_flow", f"{payload.get('market_intel_trades')} matched trades / ${payload.get('market_intel_notional')}", width - 4),
        format_kv("modules", ", ".join(payload.get("modules") or []), width - 4),
    ]
    run_lines = [
        format_kv("simulation_id", payload.get("simulation_id"), width - 4),
        format_kv("status", payload.get("run_status"), width - 4),
        format_kv("call", payload.get("forecast_call"), width - 4),
        format_kv("confidence", pct(payload.get("forecast_confidence")), width - 4),
        format_kv("total_actions", payload.get("total_actions"), width - 4),
        format_kv("top_agents", ", ".join(payload.get("top_agents") or ["n/a"]), width - 4),
    ]
    if payload.get("counterfactual_note"):
        run_lines.append(format_kv("counterfactual", payload.get("counterfactual_note"), width - 4))
    driver_lines = [
        format_kv(
            f"driver{index + 1}",
            f"{row.get('label')} [{row.get('polarity')}] strength={row.get('strength')}",
            width - 4,
        )
        for index, row in enumerate((payload.get("drivers") or [])[:4])
    ] or ["No compiled drivers yet."]
    alert_lines = [
        format_kv(
            row.get("level", "info"),
            row.get("message", ""),
            width - 4,
        )
        for row in (payload.get("alerts") or [])[:4]
    ] or ["No alerts."]
    return "\n".join(
        [
            ascii_box("PREDIHERMES CONSOLE", header_lines, width=width),
            ascii_box("MARKET BOARD", market_lines, width=width),
            ascii_box("OSINT SIGNALS", signal_lines, width=width),
            ascii_box("SIMULATION", run_lines, width=width),
            ascii_box("DECISION DRIVERS", driver_lines, width=width),
            ascii_box("ALERTS", alert_lines, width=width),
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


def cmd_compile_artifacts(args: argparse.Namespace) -> int:
    payload = compile_artifacts(
        data_root=DATA_DIR,
        mirofish_root=resolve_mirofish_root(args.mirofish_root),
        topic_id=args.topic_id,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def resolve_graph_id_from_simulation(simulation_id: str, mirofish_root: Path) -> str:
    sim_dir = mirofish_root / "backend" / "uploads" / "simulations" / simulation_id
    config_path = sim_dir / "simulation_config.json"
    if not config_path.exists():
        raise PipelineError(f"Simulation config not found for {simulation_id}: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    graph_id = str(config.get("graph_id") or "").strip()
    if not graph_id:
        raise PipelineError(f"Simulation {simulation_id} is missing graph_id in {config_path}")
    return graph_id


def cmd_profile_template(args: argparse.Namespace) -> int:
    mirofish_root = resolve_mirofish_root(args.mirofish_root)
    graph_id = str(args.graph_id or "").strip()
    if not graph_id and args.simulation_id:
        graph_id = resolve_graph_id_from_simulation(args.simulation_id, mirofish_root)
    if not graph_id:
        raise PipelineError("Provide either --graph-id or --simulation-id")

    reader = ZepEntityReader()
    filtered = reader.filter_defined_entities(
        graph_id=graph_id,
        defined_entity_types=args.entity_type or None,
        enrich_with_edges=False,
    )
    generator = OasisProfileGenerator(graph_id=graph_id)
    manifest = generator.build_profile_manifest(filtered.entities)
    manifest.update(
        {
            "graph_id": graph_id,
            "simulation_id": args.simulation_id or "",
            "rejected_count": filtered.rejected_count,
            "rejected_examples": filtered.rejected_examples,
        }
    )
    output_path = Path(args.output).expanduser() if args.output else (DATA_DIR / "profile-manifests" / f"{graph_id}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"graph_id": graph_id, "output_path": str(output_path), "entity_count": manifest["entity_count"]}, ensure_ascii=False, indent=2))
    return 0


def cmd_create_branch(args: argparse.Namespace) -> int:
    actor: Dict[str, Any] = {
        "name": args.actor_name,
        "entity_type": args.entity_type,
    }
    optional_scalar_fields = [
        ("profession", args.profession),
        ("bio", args.bio),
        ("persona", args.persona),
        ("country", args.country),
        ("mbti", args.mbti),
        ("gender", args.gender),
        ("stance", args.stance),
    ]
    for key, value in optional_scalar_fields:
        if value:
            actor[key] = value
    if args.interested_topic:
        actor["interested_topics"] = args.interested_topic
    if args.activity_level is not None:
        actor["activity_level"] = args.activity_level
    if args.influence_weight is not None:
        actor["influence_weight"] = args.influence_weight
    if args.posts_per_hour is not None:
        actor["posts_per_hour"] = args.posts_per_hour
    if args.comments_per_hour is not None:
        actor["comments_per_hour"] = args.comments_per_hour

    create_payload = request_json(
        "POST",
        f"{args.mirofish_base_url.rstrip('/')}/api/simulation/{args.base_simulation_id}/counterfactual",
        json={
            "actor": actor,
            "injection_round": int(args.injection_round),
            "opening_statement": args.opening_statement or "",
        },
    )
    data = create_payload.get("data") or {}
    output = {
        "base_simulation_id": args.base_simulation_id,
        "simulation": data.get("simulation") or {},
        "counterfactual": data.get("counterfactual") or {},
    }

    new_simulation_id = str((data.get("simulation") or {}).get("simulation_id") or "").strip()
    if args.start and new_simulation_id:
        start_payload = request_json(
            "POST",
            f"{args.mirofish_base_url.rstrip('/')}/api/simulation/start",
            json={
                "simulation_id": new_simulation_id,
                "platform": args.platform,
                "max_rounds": int(args.max_rounds),
                "enable_graph_memory_update": bool(args.enable_graph_memory_update),
            },
        )
        output["start"] = start_payload.get("data") or {}
        if args.wait:
            output["run_state"] = poll_run(args.mirofish_base_url, new_simulation_id)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    repo_root = PIPELINE_ROOT
    mirofish_root = resolve_mirofish_root(args.mirofish_root)
    compile_artifacts(
        data_root=DATA_DIR,
        mirofish_root=mirofish_root,
    )
    command = [
        "cargo",
        "run",
        "--release" if not args.debug_build else "",
        "--manifest-path",
        str(repo_root / "tools" / "predihermes_tui" / "Cargo.toml"),
        "--",
        "--data-root",
        str(DATA_DIR),
        "--compile-python",
        sys.executable,
        "--compile-script",
        str(Path(__file__).resolve()),
        "--compile-mirofish-root",
        str(mirofish_root),
        "--auto-refresh-seconds",
        "4",
    ]
    if args.topic_id:
        command.extend(["--topic-id", args.topic_id])
    command = [part for part in command if part]
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise PipelineError("Rust toolchain not found. Install cargo/rustup before launching the PrediHermes workbench.") from exc
    return 0


def cmd_command_catalog(args: argparse.Namespace) -> int:
    items = [
        "health: check WorldOSINT and MiroFish availability",
        "list-worldosint-modules: discover available WorldOSINT modules",
        "track-topic: persist a reusable topic profile",
        "update-topic: modular edits (modules, params, rounds, platform)",
        "run-tracked <topic_id> [--simulate]: execute latest pipeline path",
        "profile-template --graph-id/--simulation-id: export an operator-editable cast manifest",
        "create-branch --base-simulation-id ... --actor-name ...: create a counterfactual branch actor",
        "lookup-sim --query/--actor: resolve base + branch runs from local artifacts",
        "compile-artifacts [--topic-id]: refresh decision, evidence, accountability, and branch ledgers",
        "dashboard [--topic-id]: show ASCII run metrics in Hermes CLI",
        "tui [--topic-id] [--debug-build]: open the Rust local workbench on compiled artifacts",
    ]
    prompts = [
        "Use PrediHermes list-worldosint-modules and suggest modules for maritime conflict monitoring.",
        "Use PrediHermes dashboard for iran-conflict and summarize risk drift.",
        "Use PrediHermes compile-artifacts and tell me which topic has the strongest thesis drift.",
        "Use PrediHermes profile-template for sim_ae05684dad1b so I can edit the cast locally before rerunning.",
        "Use PrediHermes create-branch from sim_ae05684dad1b with actor Swiss backchannel envoy at round 8 and then monitor the branch.",
        "Use PrediHermes tui for the local workbench and focus on iran-conflict.",
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
    clear_market_anchor = False

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

    if args.set_topic:
        topic_record["topic"] = args.set_topic
        clear_market_anchor = True
    if args.set_market_query:
        topic_record["market_query"] = args.set_market_query
        clear_market_anchor = True
    keywords = dedupe_strings(topic_record.get("keywords") or [])
    if args.set_keyword:
        keywords = dedupe_strings(args.set_keyword)
        clear_market_anchor = True
    for keyword in args.add_keyword:
        if keyword not in keywords:
            keywords.append(keyword)
            clear_market_anchor = True
    if args.remove_keyword:
        remove_set = set(args.remove_keyword)
        keywords = [keyword for keyword in keywords if keyword not in remove_set]
        clear_market_anchor = True
    topic_record["keywords"] = keywords

    region_codes = dedupe_strings(topic_record.get("region_codes") or [])
    for code in args.add_region_code:
        if code not in region_codes:
            region_codes.append(code)
            clear_market_anchor = True
    if args.remove_region_code:
        remove_codes = set(args.remove_region_code)
        region_codes = [code for code in region_codes if code not in remove_codes]
        clear_market_anchor = True
    topic_record["region_codes"] = region_codes

    if args.set_platform:
        topic_record["platform"] = args.set_platform
    if args.set_max_rounds is not None:
        topic_record["max_rounds"] = int(args.set_max_rounds)
    if args.set_parallel_profile_count is not None:
        topic_record["parallel_profile_count"] = int(args.set_parallel_profile_count)
    if args.set_worldosint_base_url:
        topic_record["worldosint_base_url"] = args.set_worldosint_base_url
    if args.set_mirofish_base_url:
        topic_record["mirofish_base_url"] = args.set_mirofish_base_url
    if args.set_mirofish_root:
        topic_record["mirofish_root"] = args.set_mirofish_root
    if args.set_profile_overrides_path:
        topic_record["profile_overrides_path"] = args.set_profile_overrides_path
    if clear_market_anchor:
        topic_record.pop("market_anchor", None)

    topic_record["updated_at"] = iso_now()
    save_state(state)
    print(json.dumps(topic_record, ensure_ascii=False, indent=2))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    mirofish_root = resolve_mirofish_root(args.mirofish_root)
    payload = {
        "worldosint": check_worldosint_service(args.worldosint_base_url),
        "mirofish": check_service(args.mirofish_base_url, "/health"),
        "llm": check_llm_backend(mirofish_root),
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
        "use_llm_for_profiles": bool(args.use_llm_for_profiles),
        "parallel_profile_count": args.parallel_profile_count,
        "enable_graph_memory_update": bool(args.enable_graph_memory_update),
        "profile_overrides_path": args.profile_overrides_path,
        "market_anchor": {},
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
        "use_llm_for_profiles": bool(args.use_llm_for_profiles),
        "parallel_profile_count": args.parallel_profile_count,
        "enable_graph_memory_update": bool(args.enable_graph_memory_update),
        "profile_overrides_path": args.profile_overrides_path,
    }


def cmd_run_topic(args: argparse.Namespace) -> int:
    config = topic_from_args(args)
    result = run_topic(config, simulate=args.simulate, generate_report=args.generate_report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_run_tracked(args: argparse.Namespace) -> int:
    state = load_state()
    config = state.get("topics", {}).get(args.topic_id)
    if not config:
        raise PipelineError(f"Tracked topic '{args.topic_id}' does not exist")
    config = dict(config)
    config["_persist_market_anchor"] = True
    if getattr(args, "profile_overrides_path", ""):
        config["profile_overrides_path"] = args.profile_overrides_path
    result = run_topic(config, simulate=args.simulate, generate_report=args.generate_report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
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
    }

    def add_topic_config_args(target: argparse.ArgumentParser) -> None:
        target.add_argument("--market-query", default="")
        target.add_argument("--keyword", action="append", default=[])
        target.add_argument("--region-code", action="append", default=[])
        target.add_argument("--theater-region", action="append", default=[])
        target.add_argument("--headless-module", action="append", default=[])
        target.add_argument("--module-param", action="append", default=[])
        target.add_argument("--profile-overrides-path", default="")
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
    update_topic.add_argument("--set-topic", default="")
    update_topic.add_argument("--set-market-query", default="")
    update_topic.add_argument("--set-keyword", action="append", default=[])
    update_topic.add_argument("--add-keyword", action="append", default=[])
    update_topic.add_argument("--remove-keyword", action="append", default=[])
    update_topic.add_argument("--add-region-code", action="append", default=[])
    update_topic.add_argument("--remove-region-code", action="append", default=[])
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
    update_topic.add_argument("--set-worldosint-base-url", default="")
    update_topic.add_argument("--set-mirofish-base-url", default="")
    update_topic.add_argument("--set-mirofish-root", default="")
    update_topic.add_argument("--set-profile-overrides-path", default="")
    update_topic.set_defaults(func=cmd_update_topic)

    def add_run_args(run_parser: argparse.ArgumentParser, tracked: bool = False) -> None:
        if not tracked:
            run_parser.add_argument("--topic-id", default="")
            run_parser.add_argument("--topic", required=True)
            add_topic_config_args(run_parser)
        else:
            run_parser.add_argument("topic_id")
            run_parser.add_argument("--profile-overrides-path", default="")
            run_parser.add_argument("--mirofish-root", default=str(DEFAULT_MIROFISH_ROOT))
        run_parser.add_argument("--simulate", action="store_true")
        run_parser.add_argument("--generate-report", action="store_true")

    run_topic_parser = subparsers.add_parser("run-topic", help="Run an ad hoc topic through the pipeline")
    add_run_args(run_topic_parser, tracked=False)
    run_topic_parser.set_defaults(func=cmd_run_topic)

    run_tracked_parser = subparsers.add_parser("run-tracked", help="Run a saved topic through the pipeline")
    add_run_args(run_tracked_parser, tracked=True)
    run_tracked_parser.set_defaults(func=cmd_run_tracked)

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

    compile_parser = subparsers.add_parser(
        "compile-artifacts",
        help="Compile decision, evidence, accountability, and branch artifacts from local PrediHermes runs",
    )
    compile_parser.add_argument("--topic-id", default="")
    compile_parser.add_argument("--mirofish-root", default=str(DEFAULT_MIROFISH_ROOT))
    compile_parser.set_defaults(func=cmd_compile_artifacts)

    profile_template = subparsers.add_parser(
        "profile-template",
        help="Export a clean operator-editable profile manifest from a graph or simulation",
    )
    profile_template.add_argument("--graph-id", default="")
    profile_template.add_argument("--simulation-id", default="")
    profile_template.add_argument("--entity-type", action="append", default=[])
    profile_template.add_argument("--mirofish-root", default=str(DEFAULT_MIROFISH_ROOT))
    profile_template.add_argument("--output", default="")
    profile_template.set_defaults(func=cmd_profile_template)

    create_branch = subparsers.add_parser(
        "create-branch",
        help="Create a counterfactual branch by injecting a new actor into a base simulation",
    )
    create_branch.add_argument("--base-simulation-id", required=True)
    create_branch.add_argument("--actor-name", required=True)
    create_branch.add_argument("--entity-type", default="StrategicActor")
    create_branch.add_argument("--profession", default="")
    create_branch.add_argument("--bio", default="")
    create_branch.add_argument("--persona", default="")
    create_branch.add_argument("--country", default="")
    create_branch.add_argument("--mbti", default="")
    create_branch.add_argument("--gender", default="")
    create_branch.add_argument("--stance", default="")
    create_branch.add_argument("--interested-topic", action="append", default=[])
    create_branch.add_argument("--opening-statement", default="")
    create_branch.add_argument("--injection-round", type=int, default=0)
    create_branch.add_argument("--activity-level", type=float, default=None)
    create_branch.add_argument("--influence-weight", type=float, default=None)
    create_branch.add_argument("--posts-per-hour", type=float, default=None)
    create_branch.add_argument("--comments-per-hour", type=float, default=None)
    create_branch.add_argument("--start", action="store_true")
    create_branch.add_argument("--wait", action="store_true")
    create_branch.add_argument("--platform", choices=["twitter", "reddit", "parallel"], default=DEFAULT_PLATFORM)
    create_branch.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    create_branch.add_argument("--enable-graph-memory-update", action="store_true")
    create_branch.add_argument("--mirofish-base-url", default=DEFAULT_MIROFISH_BASE)
    create_branch.set_defaults(func=cmd_create_branch)

    tui = subparsers.add_parser(
        "tui",
        help="Compile artifacts and open the Rust local workbench",
    )
    tui.add_argument("--topic-id", default="")
    tui.add_argument("--mirofish-root", default=str(DEFAULT_MIROFISH_ROOT))
    tui.add_argument("--debug-build", action="store_true")
    tui.set_defaults(func=cmd_tui)

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
