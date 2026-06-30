#!/usr/bin/env /opt/hermes/.venv/bin/python3
"""Verify budget documentation integrity and live wiring.

Checks:
1. All required reference files exist
2. SKILL.md cross-references are present
3. budget-config.yaml exists and is valid YAML
4. budget-config.yaml has all required keys
5. At least one profile state.db is reachable
6. The sessions table has the expected columns
"""

from pathlib import Path
import sys
import os
import glob

ROOT = Path(__file__).resolve().parents[1]
BUDGET_CONFIG = ROOT / "references" / "budget-config.yaml"
PROFILES_ROOT = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes" / "data"))) / "profiles"

scorecard = ROOT / "references" / "post-upgrade-budget-scorecard.md"
skill = ROOT / "SKILL.md"
ladder = ROOT / "references" / "cache-aware-budget-ladder.md"
lane_model = ROOT / "references" / "lane-based-cost-model.md"
budget_config = BUDGET_CONFIG

errors = []
warnings = []

# ── 1. File existence ──────────────────────────────────────────
for path, label in [
    (scorecard, "post-upgrade-budget-scorecard.md"),
    (skill, "SKILL.md"),
    (ladder, "cache-aware-budget-ladder.md"),
    (lane_model, "lane-based-cost-model.md"),
]:
    if not path.exists():
        errors.append(f"MISSING_FILE: {label} at {path}")

# ── 2. SKILL.md cross-references ────────────────────────────────
required_skill_refs = [
    "references/cache-aware-budget-ladder.md",
    "references/post-upgrade-budget-scorecard.md",
    "references/lane-based-cost-model.md",
    "references/budget-config.yaml",
]

if skill.exists():
    skill_text = skill.read_text()
    for ref in required_skill_refs:
        if ref not in skill_text:
            errors.append(f"MISSING_SKILL_REFERENCE: {ref} not found in SKILL.md")

# ── 3. Scorecard section headers ────────────────────────────────
required_scorecard = [
    "# Post-upgrade Budget Scorecard",
    "## Core KPIs",
    "## Weekly checkpoint template",
    "## Decision rules",
    "## Scorecard rubric",
    "## Recommended first-month alert thresholds",
    "## How to present the result to the user",
]

if scorecard.exists():
    score_text = scorecard.read_text()
    for needle in required_scorecard:
        if needle not in score_text:
            errors.append(f"MISSING_SCORECARD_SECTION: {needle}")

# ── 4. budget-config.yaml existence and validity ────────────────
if not budget_config.exists():
    errors.append(f"MISSING_BUDGET_CONFIG: {budget_config} does not exist")
else:
    try:
        import yaml
        with open(budget_config) as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        errors.append(f"BUDGET_CONFIG_PARSE_ERROR: {e}")
        cfg = None

    if cfg is not None:
        # Required top-level keys
        for key in ["monthly_budget_usd", "alert_thresholds", "scorecard", "planning_bands", "beta", "production"]:
            if key not in cfg:
                errors.append(f"BUDGET_CONFIG_MISSING_KEY: {key}")

        # Alert thresholds
        if "alert_thresholds" in cfg:
            for t in ["yellow", "orange", "red"]:
                if t not in cfg["alert_thresholds"]:
                    errors.append(f"BUDGET_CONFIG_MISSING_ALERT: alert_thresholds.{t}")

        # Scorecard keys
        if "scorecard" in cfg:
            for k in ["spend_green", "spend_yellow", "spend_orange", "spend_red",
                       "effective_rate_green", "effective_rate_yellow", "effective_rate_orange", "effective_rate_red",
                       "premium_share_green", "premium_share_yellow", "premium_share_orange", "premium_share_red",
                       "cache_rate_green", "cache_rate_yellow", "cache_rate_orange", "cache_rate_red"]:
                if k not in cfg["scorecard"]:
                    errors.append(f"BUDGET_CONFIG_MISSING_SCORECARD_KEY: scorecard.{k}")

        # Planning bands
        if "planning_bands" in cfg:
            for band in ["optimistic", "base", "conservative"]:
                if band not in cfg["planning_bands"]:
                    errors.append(f"BUDGET_CONFIG_MISSING_BAND: planning_bands.{band}")

        # Beta keys
        if "beta" in cfg:
            for k in ["active", "provider", "subscription_cost_usd", "billing_period"]:
                if k not in cfg["beta"]:
                    errors.append(f"BUDGET_CONFIG_MISSING_BETA_KEY: beta.{k}")

        # Production keys
        if "production" in cfg:
            for k in ["primary_provider", "cutover_date"]:
                if k not in cfg["production"]:
                    errors.append(f"BUDGET_CONFIG_MISSING_PROD_KEY: production.{k}")

# ── 5. state.db reachability ────────────────────────────────────
state_dbs = list(PROFILES_ROOT.glob("*/state.db"))
if not state_dbs:
    errors.append("NO_STATE_DB: No profile state.db files found under ${HERMES_HOME}/profiles/")
else:
    import sqlite3
    reachable = 0
    for db_path in state_dbs:
        try:
            db = sqlite3.connect(str(db_path))
            # Check sessions table exists
            tables = [t[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "sessions" not in tables:
                warnings.append(f"STATE_DB_NO_SESSIONS: {db_path.parent.name}/state.db has no sessions table")
                continue
            # Check expected columns
            cols = [c[1] for c in db.execute("PRAGMA table_info(sessions)").fetchall()]
            required_cols = ["input_tokens", "output_tokens", "cache_read_tokens", "model"]
            missing_cols = [c for c in required_cols if c not in cols]
            if missing_cols:
                warnings.append(f"STATE_DB_MISSING_COLS: {db_path.parent.name}/state.db sessions missing {missing_cols}")
                continue
            # Check row count
            cnt = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            reachable += 1
            db.close()
        except Exception as e:
            warnings.append(f"STATE_DB_UNREADABLE: {db_path.parent.name}/state.db — {e}")

    if reachable == 0:
        errors.append("NO_REACHABLE_STATE_DB: No profile state.db files are readable with sessions table")
    else:
        print(f"STATE_DB_OK: {reachable}/{len(state_dbs)} profile databases reachable")

# ── 6. Report ───────────────────────────────────────────────────
if errors:
    print(f"\nERRORS ({len(errors)}):")
    for e in errors:
        print(f"  FAIL: {e}")

if warnings:
    print(f"\nWARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  WARN: {w}")

if not errors:
    print("\nAD_HOC_VERIFICATION_OK")
    print(f"scorecard_lines={len(scorecard.read_text().splitlines()) if scorecard.exists() else 0}")
    print(f"skill_lines={len(skill.read_text().splitlines()) if skill.exists() else 0}")
    print(f"ladder_lines={len(ladder.read_text().splitlines()) if ladder.exists() else 0}")
    print(f"lane_model_lines={len(lane_model.read_text().splitlines()) if lane_model.exists() else 0}")
    print(f"budget_config_exists={budget_config.exists()}")
    print(f"state_dbs_found={len(state_dbs)}")
    sys.exit(0)
else:
    print(f"\nVERIFICATION_FAILED: {len(errors)} errors")
    sys.exit(1)
