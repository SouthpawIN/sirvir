#!/usr/bin/env python3
"""Model Router — usage-tier aware model selection.

This router now classifies profile-level and fleet-level usage before scoring
candidate providers/models. NVIDIA-backed free lanes are available only when
the governing usage tier is light.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes" / "data")))
PROFILE_ROOT = BASE_DIR / "profiles"
ROOT_HOME = BASE_DIR / "home"
ROOT_CONFIG = BASE_DIR / "config.yaml"
ROOT_STATE_DB = BASE_DIR / "state.db"
BENCHMARK_PATH = ROOT_HOME / "benchmark_fast_results.json"
DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "references" / "usage-tier-policy.json"

WINDOW_DAYS = {"24h": 1, "7d": 7, "30d": 30}
TIER_ORDER = ["light", "moderate", "heavy", "corp"]
TIER_RANK = {name: idx + 1 for idx, name in enumerate(TIER_ORDER)}

DEPLOYED_LANE_MODELS = {
    "premium": {"glm-5.2", "glm-5", "qwen-3.7-max", "qwen3.7-max", "claude", "gpt-5.5"},
    "default": {"deepseek-v4-pro", "deepseek-v4", "gpt-5.4", "gpt-5"},
    "cheap": {"deepseek-v4-flash", "minimax-m3", "minimaxai/minimax-m3"},
}

TASK_KEYWORDS = {
    "financial": [
        "revenue", "ebitda", "irr", "valuation", "cash flow", "profit",
        "investment", "acquisition", "cap rate", "amortization", "depreciation",
        "balance sheet", "income statement", "npv", "roi", "margin",
    ],
    "creative": [
        "brand voice", "email", "headline", "copy", "marketing", "social media",
        "tagline", "messaging", "positioning", "pitch", "outreach", "campaign",
        "blog post", "press release", "newsletter",
    ],
    "coding": [
        "function", "algorithm", "debug", "refactor", "api", "class",
        "implement", "code", "script", "module", "library", "framework",
        "deploy", "ci/cd", "docker", "test", "bug", "fix",
    ],
    "operations": [
        "schedule", "dispatch", "optimize", "capacity", "logistics",
        "routing", "fleet", "inventory", "workflow", "pipeline",
    ],
    "quick": [
        "what is", "calculate", "convert", "capital of", "define",
        "how many", "when did", "who is", "translate",
    ],
    "reasoning": [
        "analyze", "compare", "should i", "strategy", "pros and cons",
        "evaluate", "assess", "recommend", "trade-off", "decision",
    ],
}

PRIORITY_WEIGHTS = {
    "speed": {"latency": 0.60, "quality": 0.25, "cost": 0.15},
    "balanced": {"latency": 0.33, "quality": 0.34, "cost": 0.33},
    "cost": {"latency": 0.15, "quality": 0.25, "cost": 0.60},
    "quality": {"latency": 0.10, "quality": 0.70, "cost": 0.20},
}

PROVIDER_COST_TIER = {
    "nvidia": 0,
    "ollama": 1,
    "ollama-cloud": 1,
    "deepseek": 2,
    "copilot": 2,
    "openai-codex": 3,
    "openai": 4,
}

QUALITY_BASELINE = {
    "gpt-5.5": 9.5,
    "gpt-5.4": 9.0,
    "gpt-5.4-mini": 8.0,
    "deepseek-v4-pro": 9.0,
    "deepseek-v4-flash": 8.2,
    "deepseek-v3.2": 8.5,
    "glm-5": 8.0,
    "glm-5.1": 8.2,
    "glm-5.2": 8.5,
    "kimi-k2:1t": 8.5,
    "kimi-k2.7-code": 8.5,
    "minimaxai/minimax-m3": 8.0,
    "minimax-m3": 8.0,
    "qwen3-coder:480b": 8.5,
    "gemma4:31b": 7.0,
}

PROVIDER_ALIASES = {
    "ollama": "ollama-cloud",
    "ollama-cloud": "ollama-cloud",
    "openai": "openai-codex",
    "openai-codex": "openai-codex",
    "nim": "nvidia",
    "nvidia": "nvidia",
}


def _normalize_provider(name: str) -> str:
    return PROVIDER_ALIASES.get((name or "").strip(), (name or "").strip())


def policy_path() -> Path:
    return Path(os.environ.get("SIRVIR_USAGE_TIER_POLICY_PATH", str(DEFAULT_POLICY_PATH)))


def load_policy() -> dict[str, Any]:
    return json.loads(policy_path().read_text())


def load_provider_snapshots(policy: dict[str, Any]) -> dict[str, Any]:
    snapshot_cfg = policy.get("provider_snapshots", {})
    path_value = snapshot_cfg.get("state_path")
    if not path_value:
        return {}
    snapshot_path = Path(path_value)
    if not snapshot_path.exists():
        return {}
    try:
        data = json.loads(snapshot_path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def apply_snapshot_adjustment(classification: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return classification
    adjusted = dict(classification)
    adjusted["reasons"] = list(classification.get("reasons", []))
    adjusted["snapshot_evidence"] = snapshot
    minimum_tier = snapshot.get("minimum_tier")
    if minimum_tier in TIER_RANK and TIER_RANK[minimum_tier] > adjusted["rank"]:
        adjusted["rank"] = TIER_RANK[minimum_tier]
        adjusted["tier"] = minimum_tier
        adjusted["reasons"].append(snapshot.get("reason") or f"provider/dashboard snapshot escalated tier to {minimum_tier}")
    return adjusted


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    lines = [raw.rstrip("\n") for raw in path.read_text().splitlines() if raw.strip() and not raw.lstrip().startswith("#")]

    def parse_scalar(text: str) -> Any:
        text = text.strip()
        if text in {"", "''", '""'}:
            return ""
        if text == "{}":
            return {}
        if text == "[]":
            return []
        if text.lower() == "true":
            return True
        if text.lower() == "false":
            return False
        if text.lower() in {"null", "none", "~"}:
            return None
        if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
            return text[1:-1]
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    def line_indent(idx: int) -> int:
        raw = lines[idx]
        return len(raw) - len(raw.lstrip(" "))

    def parse_block(start: int, indent: int) -> tuple[Any, int]:
        if start >= len(lines):
            return {}, start
        container: Any = [] if lines[start].lstrip().startswith("- ") else {}
        i = start
        while i < len(lines):
            raw = lines[i]
            current_indent = line_indent(i)
            if current_indent < indent:
                break
            if current_indent > indent:
                i += 1
                continue
            stripped = raw.strip()
            if isinstance(container, list):
                if not stripped.startswith("- "):
                    break
                item_text = stripped[2:].strip()
                if not item_text:
                    child, i = parse_block(i + 1, indent + 2)
                    container.append(child)
                    continue
                if item_text.endswith(":") and ": " not in item_text:
                    key = item_text[:-1]
                    item: dict[str, Any] = {}
                    child, next_i = parse_block(i + 1, indent + 2)
                    item[key] = child
                    container.append(item)
                    i = next_i
                    continue
                if ":" in item_text:
                    key, value = item_text.split(":", 1)
                    item = {key.strip(): parse_scalar(value)}
                    i += 1
                    while i < len(lines) and line_indent(i) > indent:
                        child_indent = line_indent(i)
                        child_text = lines[i].strip()
                        if child_text.startswith("- "):
                            child, i = parse_block(i, child_indent)
                            item.setdefault("items", child)
                            continue
                        if child_text.endswith(":") and ": " not in child_text:
                            child_key = child_text[:-1]
                            child, i = parse_block(i + 1, child_indent + 2)
                            item[child_key] = child
                            continue
                        if ":" in child_text:
                            child_key, child_value = child_text.split(":", 1)
                            item[child_key.strip()] = parse_scalar(child_value)
                        i += 1
                    container.append(item)
                    continue
                container.append(parse_scalar(item_text))
                i += 1
                continue

            if stripped.endswith(":") and ": " not in stripped:
                key = stripped[:-1]
                if i + 1 < len(lines) and line_indent(i + 1) > indent:
                    child, i = parse_block(i + 1, line_indent(i + 1))
                    container[key] = child
                else:
                    container[key] = {}
                    i += 1
                continue
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                container[key.strip()] = parse_scalar(value)
            i += 1
        return container, i

    parsed, _ = parse_block(0, line_indent(0))
    return parsed if isinstance(parsed, dict) else {}


def detect_task_type(prompt: str) -> str:
    prompt_lower = prompt.lower()
    scores = {}
    for task, keywords in TASK_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        if score > 0:
            scores[task] = score
    if not scores:
        return "reasoning"
    return max(scores, key=scores.get)


def load_benchmark() -> dict[str, Any] | None:
    if not BENCHMARK_PATH.exists():
        return None
    try:
        return json.loads(BENCHMARK_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_benchmark_scores(benchmark_data: dict[str, Any] | None) -> dict[tuple[str, str, str], dict[str, Any]]:
    scores: dict[tuple[str, str, str], dict[str, Any]] = {}
    if not benchmark_data:
        return scores
    for category, rows in benchmark_data.get("by_category", {}).items():
        for entry in rows:
            provider = _normalize_provider(entry["provider"])
            scores[(provider, entry["model"], category)] = {
                "success_rate": entry["success_rate"],
                "avg_latency_s": entry.get("avg_latency_s"),
            }
    return scores


def _rank_from_thresholds(value: float, thresholds: dict[str, float]) -> int:
    if value <= thresholds["light_max"]:
        return TIER_RANK["light"]
    if value <= thresholds["moderate_max"]:
        return TIER_RANK["moderate"]
    if value <= thresholds["heavy_max"]:
        return TIER_RANK["heavy"]
    return TIER_RANK["corp"]


def _tier_name(rank: int) -> str:
    rank = max(1, min(rank, len(TIER_ORDER)))
    return TIER_ORDER[rank - 1]


def classify_deployed_lane(model_name: str) -> str:
    model_name = (model_name or "").lower().strip()
    lane_names = sorted(
        ((lane, name) for lane, names in DEPLOYED_LANE_MODELS.items() for name in names),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    for lane, name in lane_names:
        if name in model_name:
            return lane
    return "unknown"


def _empty_window(label: str) -> dict[str, Any]:
    return {
        "window": label,
        "days": WINDOW_DAYS[label],
        "sessions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "total_tokens": 0,
        "avg_tokens_per_session": 0.0,
        "monthly_equivalent_tokens": 0.0,
        "monthly_equivalent_sessions": 0.0,
        "top_models": [],
        "top_providers": [],
    }


def profile_paths(profile: str) -> tuple[Path, Path]:
    if profile == "default":
        return ROOT_CONFIG, ROOT_STATE_DB
    return PROFILE_ROOT / profile / "config.yaml", PROFILE_ROOT / profile / "state.db"


def iter_profiles() -> list[str]:
    names = ["default"]
    if PROFILE_ROOT.exists():
        names.extend(sorted(p.name for p in PROFILE_ROOT.iterdir() if p.is_dir() and not p.name.startswith('.')))
    return names


def read_usage_windows(db_path: Path, now_ts: float) -> dict[str, Any]:
    if not db_path.exists():
        return {label: _empty_window(label) for label in WINDOW_DAYS}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception:
        return {label: _empty_window(label) for label in WINDOW_DAYS}

    result: dict[str, Any] = {}
    for label, days in WINDOW_DAYS.items():
        cutoff = now_ts - days * 86400
        row = conn.execute(
            """
            SELECT COUNT(*) AS sessions,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(cache_read_tokens), 0) AS cache_tokens
            FROM sessions
            WHERE started_at >= ?
            """,
            (cutoff,),
        ).fetchone()
        top_models = [
            dict(r) for r in conn.execute(
                """
                SELECT COALESCE(model, '') AS model,
                       COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens), 0) AS total_tokens
                FROM sessions
                WHERE started_at >= ?
                GROUP BY COALESCE(model, '')
                ORDER BY total_tokens DESC
                LIMIT 3
                """,
                (cutoff,),
            ).fetchall()
        ]
        top_providers = [
            dict(r) for r in conn.execute(
                """
                SELECT COALESCE(billing_provider, '') AS provider,
                       COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens), 0) AS total_tokens
                FROM sessions
                WHERE started_at >= ?
                GROUP BY COALESCE(billing_provider, '')
                ORDER BY total_tokens DESC
                LIMIT 3
                """,
                (cutoff,),
            ).fetchall()
        ]
        total_tokens = (row["input_tokens"] or 0) + (row["output_tokens"] or 0) + (row["cache_tokens"] or 0)
        sessions = row["sessions"] or 0
        result[label] = {
            "window": label,
            "days": days,
            "sessions": sessions,
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "cache_tokens": row["cache_tokens"] or 0,
            "total_tokens": total_tokens,
            "avg_tokens_per_session": round(total_tokens / sessions, 2) if sessions else 0.0,
            "monthly_equivalent_tokens": round((total_tokens / days) * 30, 2),
            "monthly_equivalent_sessions": round((sessions / days) * 30, 2),
            "top_models": top_models,
            "top_providers": top_providers,
        }

    conn.close()
    return result


def classify_usage_tier(windows: dict[str, Any], policy: dict[str, Any], *, scope: str) -> dict[str, Any]:
    cfg = policy["classification"]
    thresholds = cfg["profile_thresholds"] if scope == "profile" else cfg["fleet_thresholds"]
    weights = cfg["weights"]
    scores: dict[str, int] = {}
    window_scores: dict[str, Any] = {}
    reasons: list[str] = []

    for label in ("30d", "7d", "24h"):
        window = windows[label]
        token_rank = _rank_from_thresholds(window["monthly_equivalent_tokens"], thresholds["monthly_equivalent_tokens"])
        session_rank = _rank_from_thresholds(window["monthly_equivalent_sessions"], thresholds["monthly_equivalent_sessions"])
        avg_rank = _rank_from_thresholds(
            window["avg_tokens_per_session"],
            policy["classification"]["profile_thresholds"]["average_tokens_per_session"],
        )
        active_profile_rank = 0
        if scope == "fleet" and "active_profiles_30d" in thresholds:
            active_profile_rank = _rank_from_thresholds(window.get("active_profiles_30d", 0), thresholds["active_profiles_30d"])
        rank = max(token_rank, session_rank, avg_rank if scope == "profile" else token_rank, active_profile_rank)
        scores[label] = rank
        window_scores[label] = {
            "tier": _tier_name(rank),
            "rank": rank,
            "monthly_equivalent_tokens": window["monthly_equivalent_tokens"],
            "monthly_equivalent_sessions": window["monthly_equivalent_sessions"],
            "avg_tokens_per_session": window["avg_tokens_per_session"],
        }

    adjusted_24 = scores["24h"]
    daily_average_30d = windows["30d"]["total_tokens"] / 30.0 if windows["30d"]["total_tokens"] else 0.0
    outlier = False
    if cfg.get("long_term_truth_wins", True) and policy["classification"]["outlier_handling"]["enabled"] and daily_average_30d > 0:
        spike_ratio = windows["24h"]["total_tokens"] / daily_average_30d
        max_lift = policy["classification"]["outlier_handling"]["max_24h_tier_lift_above_30d"]
        if (
            windows["24h"]["total_tokens"] >= policy["classification"]["outlier_handling"]["min_24h_tokens"]
            and spike_ratio >= policy["classification"]["outlier_handling"]["spike_ratio_vs_30d_daily_average"]
            and scores["24h"] > scores["30d"] + max_lift
        ):
            adjusted_24 = min(scores["24h"], scores["30d"] + max_lift)
            outlier = True
            reasons.append(f"24h spike damped (ratio={spike_ratio:.2f}) so 30d baseline remains dominant")

    weighted = (
        scores["30d"] * weights["30d"]
        + scores["7d"] * weights["7d"]
        + adjusted_24 * weights["24h"]
    )
    rank = math.ceil(weighted) if policy["classification"].get("conservative_rounding", True) else round(weighted)

    if max(scores.values()) - min(scores.values()) >= 2:
        reasons.append("mixed windows detected; conservative upward rounding applied")

    if scope == "fleet":
        corp_cfg = policy["classification"].get("corp_escalators", {})
        if (
            windows["30d"].get("active_profiles_30d", 0) >= corp_cfg.get("min_active_profiles_30d", 999)
            and windows["30d"]["monthly_equivalent_tokens"] >= corp_cfg.get("min_monthly_equivalent_tokens", float("inf"))
            and windows["30d"].get("top_profile_share_30d", 1.0) <= corp_cfg.get("max_single_profile_share_for_corp", 0.0)
        ):
            rank = max(rank, TIER_RANK["corp"])
            reasons.append("fleet escalated to corp due to profile breadth and sustained total volume")

    needs_followup = False
    followup_question = None
    if windows["30d"].get("sessions", 0) < cfg.get("minimum_confident_sessions_30d", 3):
        needs_followup = bool(cfg.get("ask_followup_on_incomplete_evidence", False))
        if needs_followup:
            followup_question = "Is this workload representative, or is the recent history unusually sparse?"
            reasons.append("30d evidence is sparse; a short follow-up is recommended before treating this tier as durable")

    if not any(windows[label]["sessions"] for label in WINDOW_DAYS):
        rank = TIER_RANK[policy["classification"].get("default_tier_on_insufficient_evidence", "heavy")]
        reasons.append("insufficient usage evidence; conservative fallback applied")

    return {
        "tier": _tier_name(rank),
        "rank": rank,
        "weighted_score": round(weighted, 3),
        "window_scores": window_scores,
        "raw_ranks": {**scores, "24h_adjusted": adjusted_24},
        "outlier_detected": outlier,
        "needs_followup": needs_followup,
        "followup_question": followup_question,
        "reasons": reasons,
    }


def build_profile_usage(profile: str, policy: dict[str, Any], now_ts: float, snapshots: dict[str, Any] | None = None) -> dict[str, Any]:
    config_path, db_path = profile_paths(profile)
    windows = read_usage_windows(db_path, now_ts)
    config = load_yaml(config_path)
    model_cfg = config.get("model", {}) or {}
    aux_cfg = config.get("auxiliary", {}) or {}
    aux_slots = {
        name: {"provider": value.get("provider", ""), "model": value.get("model", "")}
        for name, value in aux_cfg.items()
        if isinstance(value, dict)
    }
    dominant_model_30d = windows["30d"]["top_models"][0]["model"] if windows["30d"]["top_models"] else model_cfg.get("default", "")
    profile_snapshot = ((snapshots or {}).get("profiles", {}) or {}).get(profile)
    classification = apply_snapshot_adjustment(classify_usage_tier(windows, policy, scope="profile"), profile_snapshot)
    return {
        "profile": profile,
        "config_path": str(config_path),
        "db_path": str(db_path),
        "current_main_provider": model_cfg.get("provider", ""),
        "current_main_model": model_cfg.get("default", ""),
        "current_main_lane": classify_deployed_lane(model_cfg.get("default", "")),
        "current_vision_provider": (aux_cfg.get("vision", {}) or {}).get("provider", ""),
        "current_vision_model": (aux_cfg.get("vision", {}) or {}).get("model", ""),
        "current_auxiliary_slots": aux_slots,
        "dominant_model_30d": dominant_model_30d,
        "dominant_model_lane_30d": classify_deployed_lane(dominant_model_30d),
        "windows": windows,
        "classification": classification,
        "snapshot_evidence": profile_snapshot,
    }


def build_fleet_usage(policy: dict[str, Any], now_ts: float, snapshots: dict[str, Any] | None = None) -> dict[str, Any]:
    reports = [build_profile_usage(profile, policy, now_ts, snapshots) for profile in iter_profiles()]
    fleet_windows: dict[str, Any] = {}
    for label in ("24h", "7d", "30d"):
        sessions = input_tokens = output_tokens = cache_tokens = 0
        active_profiles = 0
        token_shares = []
        for report in reports:
            window = report["windows"][label]
            sessions += window["sessions"]
            input_tokens += window["input_tokens"]
            output_tokens += window["output_tokens"]
            cache_tokens += window["cache_tokens"]
            if window["sessions"] > 0:
                active_profiles += 1
            token_shares.append(window["total_tokens"])
        total_tokens = input_tokens + output_tokens + cache_tokens
        top_share = max(token_shares) / total_tokens if total_tokens and token_shares else 1.0
        fleet_windows[label] = {
            "window": label,
            "days": WINDOW_DAYS[label],
            "sessions": sessions,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_tokens": cache_tokens,
            "total_tokens": total_tokens,
            "avg_tokens_per_session": round(total_tokens / sessions, 2) if sessions else 0.0,
            "monthly_equivalent_tokens": round((total_tokens / WINDOW_DAYS[label]) * 30, 2),
            "monthly_equivalent_sessions": round((sessions / WINDOW_DAYS[label]) * 30, 2),
            "active_profiles_30d": active_profiles,
            "top_profile_share_30d": round(top_share, 4),
        }
    fleet_snapshot = ((snapshots or {}).get("fleet", {}) or {})
    classification = apply_snapshot_adjustment(classify_usage_tier(fleet_windows, policy, scope="fleet"), fleet_snapshot)
    return {
        "profiles": reports,
        "windows": fleet_windows,
        "classification": classification,
        "snapshot_evidence": fleet_snapshot,
    }


def load_overrides(policy: dict[str, Any]) -> list[dict[str, Any]]:
    override_path = Path(policy["overrides"]["state_path"])
    if not override_path.exists():
        return []
    try:
        data = json.loads(override_path.read_text())
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("overrides", [])
    return []


def resolve_override(profile: str, policy: dict[str, Any], now_ts: float) -> dict[str, Any] | None:
    required = set(policy.get("overrides", {}).get("required_fields", []))
    for entry in load_overrides(policy):
        if required and not required.issubset(entry):
            continue
        target = entry.get("target")
        scope = entry.get("scope")
        start_at = entry.get("start_at")
        expires_at = entry.get("expires_at")
        if scope not in {"profile", "fleet"}:
            continue
        if scope == "profile" and target != profile:
            continue
        if scope == "fleet" and target not in {None, "all", "fleet", "default"}:
            continue
        try:
            start_ts = float(start_at)
            expiry_ts = float(expires_at)
        except (TypeError, ValueError):
            continue
        if start_ts > now_ts or expiry_ts <= now_ts:
            continue
        return entry
    return None


def build_migration_suggestions(profile_usage: dict[str, Any], winner: dict[str, Any], governing_tier: str) -> list[str]:
    suggestions: list[str] = []
    current_provider = profile_usage["current_main_provider"]
    current_model = profile_usage["current_main_model"]
    if current_provider != winner["provider"] or current_model != winner["model"]:
        suggestions.append(
            f"Main recommendation differs from deployed config: move {current_provider}/{current_model} to {winner['provider']}/{winner['model']} when ready."
        )
    nvidia_aux_slots = [
        f"{name}={slot.get('provider','')}/{slot.get('model','')}"
        for name, slot in sorted(profile_usage.get("current_auxiliary_slots", {}).items())
        if slot.get("provider") == "nvidia"
    ]
    if nvidia_aux_slots and governing_tier != "light":
        suggestions.append(
            f"NVIDIA aux slots under governing tier {governing_tier} are migration candidates: {', '.join(nvidia_aux_slots)}."
        )
    return suggestions


def candidate_matrix() -> dict[str, list[tuple[str, str]]]:
    return {
        "financial": [
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("nvidia", "deepseek-v4-pro"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("nvidia", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
        "creative": [
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("nvidia", "deepseek-v4-flash"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
        "coding": [
            ("ollama-cloud", "kimi-k2.7-code"),
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "qwen3-coder:480b"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("openai-codex", "gpt-5.4"),
        ],
        "operations": [
            ("ollama-cloud", "deepseek-v4-pro"),
            ("nvidia", "deepseek-v4-flash"),
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
        "quick": [
            ("nvidia", "deepseek-v4-flash"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("openai-codex", "gpt-5.4"),
        ],
        "reasoning": [
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("nvidia", "deepseek-v4-pro"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
    }


def score_model(provider: str, model: str, task_type: str, priority: str, benchmark_scores: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any] | None:
    bm = benchmark_scores.get((provider, model, task_type), {})
    success_rate = bm.get("success_rate", 100.0)
    avg_latency = bm.get("avg_latency_s")
    if success_rate == 0.0:
        return None

    weights = PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["balanced"])
    if avg_latency is not None:
        latency_score = max(0.5, min(10.0, 10.0 - 2.5 * (avg_latency ** 0.5)))
    else:
        latency_score = 5.0

    quality_score = QUALITY_BASELINE.get(model, 7.0)
    cost_tier = PROVIDER_COST_TIER.get(provider, 3)
    cost_score = max(1.0, 10.0 - (cost_tier * 2.5))
    weighted = (
        weights["latency"] * latency_score
        + weights["quality"] * quality_score
        + weights["cost"] * cost_score
    )
    return {
        "model": model,
        "provider": provider,
        "latency_score": round(latency_score, 2),
        "quality_score": round(quality_score, 2),
        "cost_score": round(cost_score, 2),
        "weighted_score": round(weighted, 2),
        "avg_latency_s": avg_latency,
        "success_rate": success_rate,
        "lane_hint": "free" if provider == "nvidia" else ("paid" if provider == "openai-codex" else "subscription"),
    }


def gate_candidate(provider: str, governing_tier: str, policy: dict[str, Any]) -> tuple[bool, str | None]:
    if provider == "nvidia" and governing_tier not in set(policy["provider_policy"]["nvidia"]["allowed_tiers"]):
        return False, f"NVIDIA gated off because governing tier is {governing_tier}"
    return True, None


def build_recommendation_lanes(scored: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    best = scored[0] if scored else None
    cheapest = next((s for s in scored if s["provider"] == "nvidia"), None) or next((s for s in scored if s["provider"] == "ollama-cloud"), None) or best
    safest = next((s for s in scored if s["provider"] == "openai-codex"), None) or next((s for s in scored if s["provider"] == "ollama-cloud"), None) or best
    return {"best": best, "cheaper": cheapest, "safest": safest}


def current_time_ts() -> float:
    env_value = os.environ.get("SIRVIR_USAGE_TIER_NOW_TS")
    if env_value:
        try:
            return float(env_value)
        except ValueError:
            pass
    return datetime.now(timezone.utc).timestamp()


def select_model(task_type: str, priority: str = "balanced", prompt: str | None = None, high_stakes: bool = False, profile: str = "sirvir", allow_conservative_fallback: bool = False) -> tuple[str | None, dict[str, Any]]:
    if task_type == "auto":
        if not prompt:
            return None, {"error": "prompt required for auto-detection"}
        task_type = detect_task_type(prompt)

    policy = load_policy()
    snapshots = load_provider_snapshots(policy)
    now_ts = current_time_ts()
    profile_usage = build_profile_usage(profile, policy, now_ts, snapshots)
    fleet_usage = build_fleet_usage(policy, now_ts, snapshots)

    profile_tier = profile_usage["classification"]["tier"]
    fleet_tier = fleet_usage["classification"]["tier"]
    governing_tier = fleet_tier if policy["provider_policy"]["governing_tier_rule"] == "fleet_wins_by_default" else profile_tier

    override = resolve_override(profile, policy, now_ts)
    if override:
        governing_tier = override.get("override_tier", governing_tier)

    benchmark_data = load_benchmark()
    benchmark_scores = get_benchmark_scores(benchmark_data)

    candidates = candidate_matrix().get(task_type, candidate_matrix()["reasoning"])
    scored: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for provider, model in candidates:
        allowed, reason = gate_candidate(provider, governing_tier, policy)
        if not allowed:
            excluded.append({"provider": provider, "model": model, "reason": reason})
            continue
        result = score_model(provider, model, task_type, priority, benchmark_scores)
        if result is None:
            excluded.append({"provider": provider, "model": model, "reason": "benchmark reported 0% success"})
            continue
        scored.append(result)

    if high_stakes:
        for item in scored:
            if item["provider"] in ("openai-codex", "ollama-cloud"):
                item["weighted_score"] = round(item["weighted_score"] + 1.0, 2)

    scored.sort(key=lambda row: row["weighted_score"], reverse=True)
    if not scored:
        return None, {
            "error": f"No available models for task '{task_type}'.",
            "excluded_candidates": excluded,
            "profile_tier": profile_tier,
            "fleet_tier": fleet_tier,
            "governing_tier": governing_tier,
        }

    lanes = build_recommendation_lanes(scored)
    winner = lanes["best"]
    assert winner is not None
    migration_suggestions = build_migration_suggestions(profile_usage, winner, governing_tier)
    followup_required = bool(profile_usage["classification"].get("needs_followup") or fleet_usage["classification"].get("needs_followup"))
    followup_question = profile_usage["classification"].get("followup_question") or fleet_usage["classification"].get("followup_question")
    if followup_required and not allow_conservative_fallback:
        return None, {
            "error": "followup required before recommendation",
            "followup_required": True,
            "followup_question": followup_question,
            "profile": profile,
            "profile_tier": profile_tier,
            "fleet_tier": fleet_tier,
            "governing_tier": governing_tier,
            "override_active": bool(override),
            "override": override,
            "temporary_override_supported": bool(policy.get("overrides", {}).get("allow_temporary_overrides", False)),
            "profile_evidence": profile_usage["classification"],
            "fleet_evidence": fleet_usage["classification"],
            "excluded_candidates": excluded,
            "snapshot_evidence": {
                "profile": profile_usage.get("snapshot_evidence"),
                "fleet": fleet_usage.get("snapshot_evidence"),
            },
        }
    return winner["model"], {
        "model": winner["model"],
        "provider": winner["provider"],
        "task_type": task_type,
        "priority": priority,
        "high_stakes": high_stakes,
        "followup_required": False,
        "followup_question": followup_question,
        "weighted_score": winner["weighted_score"],
        "latency_score": winner["latency_score"],
        "quality_score": winner["quality_score"],
        "cost_score": winner["cost_score"],
        "avg_latency_s": winner["avg_latency_s"],
        "success_rate": winner["success_rate"],
        "profile": profile,
        "profile_tier": profile_tier,
        "fleet_tier": fleet_tier,
        "governing_tier": governing_tier,
        "nvidia_eligible": governing_tier in set(policy["provider_policy"]["nvidia"]["allowed_tiers"]),
        "override_active": bool(override),
        "override": override,
        "migration_suggestions": migration_suggestions,
        "temporary_override_supported": bool(policy.get("overrides", {}).get("allow_temporary_overrides", False)),
        "profile_evidence": profile_usage["classification"],
        "fleet_evidence": fleet_usage["classification"],
        "recommendation_lanes": lanes,
        "excluded_candidates": excluded,
        "alternatives": [
            {"model": s["model"], "provider": s["provider"], "score": s["weighted_score"]}
            for s in scored[1:4]
        ],
        "benchmark_age": benchmark_data["generated_at"] if benchmark_data else "no benchmark data",
        "current_main_provider": profile_usage["current_main_provider"],
        "current_main_model": profile_usage["current_main_model"],
        "current_main_lane": profile_usage["current_main_lane"],
        "current_vision_provider": profile_usage["current_vision_provider"],
        "current_vision_model": profile_usage["current_vision_model"],
        "dominant_model_30d": profile_usage["dominant_model_30d"],
        "dominant_model_lane_30d": profile_usage["dominant_model_lane_30d"],
        "snapshot_evidence": {
            "profile": profile_usage.get("snapshot_evidence"),
            "fleet": fleet_usage.get("snapshot_evidence"),
        },
    }


def list_routing_table(profile: str) -> None:
    benchmark_data = load_benchmark()
    print("Model Routing Table")
    print(f"Benchmark: {benchmark_data['generated_at'] if benchmark_data else 'NONE — using baselines'}")
    print(f"Profile: {profile}")
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print()

    for task_type in ["financial", "creative", "coding", "operations", "quick", "reasoning"]:
        print(f"## {task_type.title()}")
        print(f"{'Priority':<12} {'Model':<25} {'Provider':<15} {'Tier':<10} {'Score':<8}")
        print("-" * 84)
        for priority in ["speed", "balanced", "cost", "quality"]:
            model, details = select_model(task_type, priority, profile=profile)
            if model:
                print(
                    f"{priority:<12} {model:<25} {details['provider']:<15} {details['governing_tier']:<10} {details['weighted_score']:<8.2f}"
                )
            else:
                print(f"{priority:<12} {'NO MODEL AVAILABLE':<25} {'—':<15} {'—':<10} {'—':<8}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Usage-tier aware model router")
    parser.add_argument("--task", choices=["financial", "creative", "coding", "operations", "quick", "reasoning", "auto"], help="Task type")
    parser.add_argument("--priority", choices=["speed", "balanced", "cost", "quality"], default="balanced", help="Optimization priority")
    parser.add_argument("--prompt", help="Prompt text (required for --task auto)")
    parser.add_argument("--high-stakes", action="store_true", help="Prefer reliability over cost")
    parser.add_argument("--profile", default="sirvir", help="Profile to classify and route for")
    parser.add_argument("--allow-conservative-fallback", action="store_true", help="Use conservative fallback immediately when evidence is incomplete")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--list", action="store_true", help="Print full routing table")
    args = parser.parse_args()

    if args.list:
        list_routing_table(args.profile)
        return

    if not args.task:
        parser.error("--task or --list required")

    model, details = select_model(args.task, args.priority, args.prompt, args.high_stakes, args.profile, args.allow_conservative_fallback)
    if model is None:
        if args.json:
            print(json.dumps(details, indent=2))
        else:
            print(f"ERROR: {details.get('error', 'unknown')}")
            if details.get("followup_question"):
                print(f"Follow-up:       {details['followup_question']}")
            if details.get("provisional_recommendation"):
                provisional = details["provisional_recommendation"]
                print(f"Provisional:     {provisional['provider']}/{provisional['model']} ({provisional['weighted_score']})")
        sys.exit(1)

    if args.json:
        print(json.dumps(details, indent=2))
        return

    print(f"Task:            {details['task_type']}")
    print(f"Priority:        {details['priority']}")
    print(f"Profile:         {details['profile']}")
    print(f"Profile Tier:    {details['profile_tier']}")
    print(f"Fleet Tier:      {details['fleet_tier']}")
    print(f"Governing Tier:  {details['governing_tier']}")
    print(f"Current Lane:    {details['current_main_lane']}")
    print(f"30d Dominant:    {details['dominant_model_30d']} ({details['dominant_model_lane_30d']})")
    print(f"Model:           {model}")
    print(f"Provider:        {details['provider']}")
    print(f"Score:           {details['weighted_score']:.2f}")
    if details['avg_latency_s']:
        print(f"Latency:         {details['avg_latency_s']:.2f}s")
    print(f"Success:         {details['success_rate']}%")
    print(f"NVIDIA Eligible: {details['nvidia_eligible']}")
    if details.get("high_stakes"):
        print("Mode:            HIGH-STAKES")
    if details["profile_evidence"]["reasons"]:
        print("Profile Notes:")
        for reason in details["profile_evidence"]["reasons"]:
            print(f"  - {reason}")
    if details["fleet_evidence"]["reasons"]:
        print("Fleet Notes:")
        for reason in details["fleet_evidence"]["reasons"]:
            print(f"  - {reason}")
    if details["migration_suggestions"]:
        print("Migration:")
        for suggestion in details["migration_suggestions"]:
            print(f"  - {suggestion}")
    if details["excluded_candidates"]:
        print("Excluded:")
        for row in details["excluded_candidates"][:5]:
            print(f"  - {row['provider']}/{row['model']}: {row['reason']}")
    print("Lanes:")
    for lane_name, lane in details["recommendation_lanes"].items():
        if lane:
            print(f"  - {lane_name}: {lane['provider']}/{lane['model']} ({lane['weighted_score']})")


if __name__ == "__main__":
    main()