#!/usr/bin/env python3
"""Fleet audit: usage-tier aware profile and fleet usage summary.

Run this first when setting up or reviewing sirvir-budget / sirvir routing.
It will:
1. Discover active profiles, including the root default profile
2. Read each profile's config.yaml to see deployed models/providers
3. Read each profile's state.db to aggregate usage over 24h / 7d / 30d
4. Compute profile-level usage tiers from historical behavior
5. Print a fleet-wide summary with cache rates, cost, and governing evidence

For per-session token usage and cost, use the native Hermes `/usage` slash
command. This audit answers the fleet-wide question: "what is the fleet
spending, and which profiles dominate?"
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes" / "data")))
PROFILE_ROOT = BASE_DIR / "profiles"
ROOT_PROFILE = "default"
ROOT_CONFIG = BASE_DIR / "config.yaml"
ROOT_STATE_DB = BASE_DIR / "state.db"
DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent.parent / "sirvir" / "references" / "usage-tier-policy.json"

WINDOW_DAYS = {"24h": 1, "7d": 7, "30d": 30}
TIER_ORDER = ["light", "moderate", "heavy", "corp"]
TIER_RANK = {name: idx + 1 for idx, name in enumerate(TIER_ORDER)}

DEPLOYED_LANE_MODELS = {
    "premium": {"glm-5.2", "glm-5", "qwen-3.7-max", "qwen3.7-max", "claude", "gpt-5.5"},
    "default": {"deepseek-v4-pro", "deepseek-v4", "gpt-5.4", "gpt-5"},
    "cheap": {"deepseek-v4-flash", "minimax-m3", "minimaxai/minimax-m3"},
}


@dataclass
class ProfileEntry:
    name: str
    config_path: Path
    db_path: Path


def policy_path() -> Path:
    return Path(os.environ.get("SIRVIR_USAGE_TIER_POLICY_PATH", str(DEFAULT_POLICY_PATH)))


def load_policy() -> dict[str, Any]:
    return json.loads(policy_path().read_text())


def resolve_policy_state_path(path_value: str) -> Path:
    skill_dir = DEFAULT_POLICY_PATH.parent.parent
    expanded = (path_value or "").replace("${SIRVIR_SKILL_DIR}", str(skill_dir)).replace("${HERMES_HOME}", str(BASE_DIR))
    return Path(os.path.expandvars(expanded))


def load_provider_snapshots(policy: dict[str, Any]) -> dict[str, Any]:
    snapshot_cfg = policy.get("provider_snapshots", {})
    path_value = snapshot_cfg.get("state_path")
    if not path_value:
        return {}
    snapshot_path = resolve_policy_state_path(path_value)
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

    if not lines:
        return {}
    parsed, _ = parse_block(0, line_indent(0))
    return parsed if isinstance(parsed, dict) else {}


def iter_profiles() -> list[ProfileEntry]:
    entries = [ProfileEntry(ROOT_PROFILE, ROOT_CONFIG, ROOT_STATE_DB)]
    if PROFILE_ROOT.exists():
        for child in sorted(PROFILE_ROOT.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                entries.append(ProfileEntry(child.name, child / "config.yaml", child / "state.db"))
    return entries


def extract_config_summary(config: dict[str, Any]) -> dict[str, Any]:
    model = config.get("model", {}) or {}
    aux = config.get("auxiliary", {}) or {}
    return {
        "main_provider": model.get("provider", ""),
        "main_model": model.get("default", ""),
        "vision_provider": (aux.get("vision", {}) or {}).get("provider", ""),
        "vision_model": (aux.get("vision", {}) or {}).get("model", ""),
        "web_extract_provider": (aux.get("web_extract", {}) or {}).get("provider", ""),
        "web_extract_model": (aux.get("web_extract", {}) or {}).get("model", ""),
        "compression_provider": (aux.get("compression", {}) or {}).get("provider", ""),
        "compression_model": (aux.get("compression", {}) or {}).get("model", ""),
    }


def _empty_window(label: str) -> dict[str, Any]:
    return {
        "window": label,
        "days": WINDOW_DAYS[label],
        "sessions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "cost_usd": 0.0,
        "total_tokens": 0,
        "avg_tokens_per_session": 0.0,
        "distinct_days": 0,
        "top_models": [],
        "top_providers": [],
        "daily_totals": [],
        "monthly_equivalent_tokens": 0.0,
        "monthly_equivalent_sessions": 0.0,
    }


def _rank_from_thresholds(value: float, thresholds: dict[str, float]) -> int:
    if value <= thresholds["light_max"]:
        return TIER_RANK["light"]
    if value <= thresholds["moderate_max"]:
        return TIER_RANK["moderate"]
    if value <= thresholds["heavy_max"]:
        return TIER_RANK["heavy"]
    return TIER_RANK["corp"]


def _tier_name(rank: int) -> str:
    rank = max(1, min(rank, 4))
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


def summarize_db(db_path: Path, now_ts: float) -> dict[str, Any]:
    if not db_path.exists():
        return {label: _empty_window(label) for label in WINDOW_DAYS}

    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
    except Exception:
        return {label: _empty_window(label) for label in WINDOW_DAYS}

    windows: dict[str, Any] = {}
    for label, days in WINDOW_DAYS.items():
        cutoff = now_ts - (days * 86400)
        try:
            row = db.execute(
                """
                SELECT COUNT(*) AS sessions,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(cache_read_tokens), 0) AS cache_tokens,
                       COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 0) AS cost_usd,
                       COUNT(DISTINCT DATE(started_at, 'unixepoch')) AS distinct_days
                FROM sessions
                WHERE started_at >= ?
                """,
                (cutoff,),
            ).fetchone()

            top_models = [
                dict(r)
                for r in db.execute(
                    """
                    SELECT COALESCE(model, '') AS model,
                           COUNT(*) AS sessions,
                           COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens), 0) AS total_tokens
                    FROM sessions
                    WHERE started_at >= ?
                    GROUP BY COALESCE(model, '')
                    ORDER BY total_tokens DESC
                    LIMIT 5
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            top_providers = [
                dict(r)
                for r in db.execute(
                    """
                    SELECT COALESCE(billing_provider, '') AS provider,
                           COUNT(*) AS sessions,
                           COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens), 0) AS total_tokens
                    FROM sessions
                    WHERE started_at >= ?
                    GROUP BY COALESCE(billing_provider, '')
                    ORDER BY total_tokens DESC
                    LIMIT 5
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            daily_totals = [
                dict(r)
                for r in db.execute(
                    """
                    SELECT DATE(started_at, 'unixepoch') AS day,
                           COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens), 0) AS total_tokens,
                           COUNT(*) AS sessions
                    FROM sessions
                    WHERE started_at >= ?
                    GROUP BY DATE(started_at, 'unixepoch')
                    ORDER BY day ASC
                    """,
                    (cutoff,),
                ).fetchall()
            ]

            total_tokens = (row["input_tokens"] or 0) + (row["output_tokens"] or 0) + (row["cache_tokens"] or 0)
            sessions = row["sessions"] or 0
            windows[label] = {
                "window": label,
                "days": days,
                "sessions": sessions,
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
                "cache_tokens": row["cache_tokens"] or 0,
                "cost_usd": round(row["cost_usd"] or 0.0, 2),
                "total_tokens": total_tokens,
                "avg_tokens_per_session": round(total_tokens / sessions, 2) if sessions else 0.0,
                "distinct_days": row["distinct_days"] or 0,
                "top_models": top_models,
                "top_providers": top_providers,
                "daily_totals": daily_totals,
                "monthly_equivalent_tokens": round((total_tokens / days) * 30, 2),
                "monthly_equivalent_sessions": round((sessions / days) * 30, 2),
            }
        except Exception:
            windows[label] = _empty_window(label)

    db.close()
    return windows


def classify_usage_tier(windows: dict[str, Any], policy: dict[str, Any], *, scope: str) -> dict[str, Any]:
    cfg = policy["classification"]
    thresholds = cfg["profile_thresholds"] if scope == "profile" else cfg["fleet_thresholds"]
    weights = cfg["weights"]
    corp_escalators = cfg.get("corp_escalators", {})

    per_window: dict[str, Any] = {}
    scores: dict[str, int] = {}
    reasons: list[str] = []

    for label in ("30d", "7d", "24h"):
        window = windows.get(label, _empty_window(label))
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
        per_window[label] = {
            "tier": _tier_name(rank),
            "rank": rank,
            "monthly_equivalent_tokens": window["monthly_equivalent_tokens"],
            "monthly_equivalent_sessions": window["monthly_equivalent_sessions"],
            "avg_tokens_per_session": window["avg_tokens_per_session"],
        }

    adjusted_24_rank = scores["24h"]
    outlier = False
    daily_average_30d = (windows["30d"]["total_tokens"] / 30.0) if windows["30d"]["total_tokens"] else 0.0
    if cfg.get("long_term_truth_wins", True) and cfg["outlier_handling"]["enabled"] and daily_average_30d > 0:
        spike_ratio = windows["24h"]["total_tokens"] / daily_average_30d
        max_lift = cfg["outlier_handling"]["max_24h_tier_lift_above_30d"]
        if (
            windows["24h"]["total_tokens"] >= cfg["outlier_handling"]["min_24h_tokens"]
            and spike_ratio >= cfg["outlier_handling"]["spike_ratio_vs_30d_daily_average"]
            and scores["24h"] > scores["30d"] + max_lift
        ):
            adjusted_24_rank = min(scores["24h"], scores["30d"] + max_lift)
            outlier = True
            reasons.append(
                f"24h activity looks like an outlier spike (ratio={spike_ratio:.2f}); damped to preserve 30d truth"
            )

    weighted_score = (
        (scores["30d"] * weights["30d"])
        + (scores["7d"] * weights["7d"])
        + (adjusted_24_rank * weights["24h"])
    )
    conservative_rank = math.ceil(weighted_score) if cfg.get("conservative_rounding", True) else round(weighted_score)

    if max(scores.values()) - min(scores.values()) >= 2:
        reasons.append("mixed evidence across windows; conservative upward rounding applied")

    if scope == "fleet":
        active_profiles = windows["30d"].get("active_profiles_30d", 0)
        top_share = windows["30d"].get("top_profile_share_30d", 1.0)
        if (
            active_profiles >= corp_escalators.get("min_active_profiles_30d", 999)
            and windows["30d"]["monthly_equivalent_tokens"] >= corp_escalators.get("min_monthly_equivalent_tokens", float("inf"))
            and top_share <= corp_escalators.get("max_single_profile_share_for_corp", 0.0)
        ):
            conservative_rank = max(conservative_rank, TIER_RANK["corp"])
            reasons.append("fleet escalated to corp due to active-profile breadth and aggregate volume")

    needs_followup = False
    followup_question = None
    if windows["30d"].get("sessions", 0) < cfg.get("minimum_confident_sessions_30d", 3):
        needs_followup = bool(cfg.get("ask_followup_on_incomplete_evidence", False))
        if needs_followup:
            followup_question = "Is this workload representative, or is the recent history unusually sparse?"
            reasons.append("30d evidence is sparse; a short follow-up is recommended before treating this tier as durable")

    if windows["30d"]["sessions"] == 0 and windows["7d"]["sessions"] == 0 and windows["24h"]["sessions"] == 0:
        conservative_rank = TIER_RANK[cfg.get("default_tier_on_insufficient_evidence", "heavy")]
        reasons.append("insufficient evidence; conservative fallback tier applied")

    return {
        "tier": _tier_name(conservative_rank),
        "rank": conservative_rank,
        "weighted_score": round(weighted_score, 3),
        "window_scores": per_window,
        "raw_ranks": {**scores, "24h_adjusted": adjusted_24_rank},
        "outlier_detected": outlier,
        "needs_followup": needs_followup,
        "followup_question": followup_question,
        "reasons": reasons,
    }


def build_profile_report(entry: ProfileEntry, policy: dict[str, Any], now_ts: float, snapshots: dict[str, Any] | None = None) -> dict[str, Any]:
    config = load_yaml(entry.config_path)
    windows = summarize_db(entry.db_path, now_ts)
    profile_snapshot = ((snapshots or {}).get("profiles", {}) or {}).get(entry.name)
    classification = apply_snapshot_adjustment(classify_usage_tier(windows, policy, scope="profile"), profile_snapshot)
    summary = extract_config_summary(config)
    cache_den = windows["30d"]["input_tokens"] + windows["30d"]["cache_tokens"]
    cache_rate = (100.0 * windows["30d"]["cache_tokens"] / cache_den) if cache_den else 0.0
    dominant_model = windows["30d"]["top_models"][0]["model"] if windows["30d"]["top_models"] else summary["main_model"]
    return {
        "profile": entry.name,
        "config_path": str(entry.config_path),
        "db_path": str(entry.db_path),
        "config": summary,
        "deployed_lane": classify_deployed_lane(summary["main_model"]),
        "dominant_model_30d": dominant_model,
        "dominant_model_lane": classify_deployed_lane(dominant_model),
        "windows": windows,
        "classification": classification,
        "snapshot_evidence": profile_snapshot,
        "cache_rate_30d": round(cache_rate, 2),
    }


def build_fleet_report(reports: list[dict[str, Any]], policy: dict[str, Any], snapshots: dict[str, Any] | None = None) -> dict[str, Any]:
    fleet_windows: dict[str, Any] = {}
    for label in ("24h", "7d", "30d"):
        totals = Counter()
        active_profiles = 0
        profile_token_pairs: list[tuple[str, int]] = []
        for report in reports:
            window = report["windows"][label]
            totals["sessions"] += window["sessions"]
            totals["input_tokens"] += window["input_tokens"]
            totals["output_tokens"] += window["output_tokens"]
            totals["cache_tokens"] += window["cache_tokens"]
            if window["sessions"] > 0:
                active_profiles += 1
            profile_token_pairs.append((report["profile"], window["total_tokens"]))

        total_tokens = totals["input_tokens"] + totals["output_tokens"] + totals["cache_tokens"]
        top_profile_share = 1.0
        if total_tokens > 0:
            top_profile_share = max(tokens for _, tokens in profile_token_pairs) / total_tokens

        fleet_windows[label] = {
            "window": label,
            "days": WINDOW_DAYS[label],
            "sessions": totals["sessions"],
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
            "cache_tokens": totals["cache_tokens"],
            "total_tokens": total_tokens,
            "avg_tokens_per_session": round(total_tokens / totals["sessions"], 2) if totals["sessions"] else 0.0,
            "monthly_equivalent_tokens": round((total_tokens / WINDOW_DAYS[label]) * 30, 2),
            "monthly_equivalent_sessions": round((totals["sessions"] / WINDOW_DAYS[label]) * 30, 2),
            "active_profiles_30d": active_profiles if label == "30d" else active_profiles,
            "top_profile_share_30d": round(top_profile_share, 4) if label == "30d" else round(top_profile_share, 4),
        }

    fleet_snapshot = ((snapshots or {}).get("fleet", {}) or {})
    classification = apply_snapshot_adjustment(classify_usage_tier(fleet_windows, policy, scope="fleet"), fleet_snapshot)
    return {"windows": fleet_windows, "classification": classification}


def render_text(reports: list[dict[str, Any]], fleet: dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 88)
    lines.append("SIRVIR FLEET USAGE-TIER AUDIT")
    lines.append("=" * 88)
    lines.append(
        f"Fleet tier: {fleet['classification']['tier']}  |  30d monthly-equiv tokens: {fleet['windows']['30d']['monthly_equivalent_tokens']:,.0f}"
    )
    if fleet["classification"]["reasons"]:
        for reason in fleet["classification"]["reasons"]:
            lines.append(f"  - {reason}")
    lines.append("")

    for report in reports:
        cfg = report["config"]
        w30 = report["windows"]["30d"]
        cls = report["classification"]
        lines.append(f"-- {report['profile']} --")
        lines.append(
            f"  Tier:    {cls['tier']}  |  30d tokens={w30['total_tokens']:,}  sessions={w30['sessions']}  cache={report['cache_rate_30d']:.1f}%"
        )
        lines.append(
            f"  Lanes:   deployed={report['deployed_lane']}  dominant_model_30d={report['dominant_model_lane']}"
        )
        lines.append(
            f"  Config:  main={cfg['main_provider']}/{cfg['main_model']}  vision={cfg['vision_provider']}/{cfg['vision_model']}"
        )
        lines.append(
            f"  Windows: 30d={cls['window_scores']['30d']['tier']}  7d={cls['window_scores']['7d']['tier']}  24h={cls['window_scores']['24h']['tier']}"
        )
        if cls["reasons"]:
            for reason in cls["reasons"]:
                lines.append(f"    - {reason}")
        top_models = ", ".join(m["model"] or "<unset>" for m in w30["top_models"][:3])
        if top_models:
            lines.append(f"  Top 30d models: {top_models}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Usage-tier aware fleet audit")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    parser.add_argument("--profile", help="Filter to a single profile name")
    args = parser.parse_args()

    policy = load_policy()
    snapshots = load_provider_snapshots(policy)
    now_ts = datetime.now(timezone.utc).timestamp()
    all_reports = [build_profile_report(entry, policy, now_ts, snapshots) for entry in iter_profiles()]
    fleet = build_fleet_report(all_reports, policy, snapshots)
    reports = all_reports
    if args.profile:
        reports = [r for r in reports if r["profile"] == args.profile]

    if args.json:
        print(json.dumps({"fleet": fleet, "profiles": reports}, indent=2))
    else:
        print(render_text(reports, fleet))


if __name__ == "__main__":
    main()
