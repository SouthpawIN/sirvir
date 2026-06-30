---
name: sirvir-budget
description: "Token usage monitoring and budget skill. Documents how to read Hermes state.db for real usage data, track spending against a monthly budget, set alert thresholds (75% yellow, 90% orange, 100% red), and suggest upgrades/downgrades based on utilization. Complements the turbofit core skill — turbofit serves models, sirvir-budget tracks what they cost."
version: 1.2.0
author: example-user
license: MIT
tags: [budget, token-usage, cost-tracking, state-db, alerts, spending, turbofit]
metadata:
  hermes:
    tags: [budget, token-usage, cost-tracking, state-db, alerts, spending]
    related_skills: [turbofit, sirvir-research, sirvir-serve]
  changelog: |
    1.2.0 (2026-06-29): Added Cost Spectrum Analysis methodology (interview-driven, 5-step process). Added root profile pitfall (${HERMES_STATE_DB}). Added cache savings pitfall (consistent prompt token bases). Fixed all budget-config.yaml path references (turbofit -> sirvir-budget). Updated lane-based-cost-model with new tier assignments and empirically verified constraints. Added cost-spectrum.md reference.
    1.1.0 (2026-06-29): Fixed state.db path (per-profile, not ~/.hermes). Replaced sqlite3 CLI queries with Python sqlite3 (sqlite3 CLI not installed). Added beta-period effective-cost computation. Updated budget config reference to live file. Added fleet-wide aggregate query.
    1.0.0 (2026-06-26): Initial split from turbofit monolith. Wraps the state.db usage queries, monthly budget tracking, alert thresholds, and upgrade/downgrade suggestion logic.
---

# Sirvir-Budget — Token Usage Monitoring & Budget

This skill is the **cost layer** of the Sirvir model fleet. The turbofit core skill serves models; sirvir-budget tracks what they actually cost — reading real usage from Hermes `state.db`, projecting monthly spend, alerting when thresholds are hit, and suggesting upgrades or downgrades based on utilization. The daily 6:00 AM research cron delegates the budget check to this workflow.

## Relationship with native Hermes /usage

Hermes Agent ships a native `/usage` slash command that shows per-session token usage, cost breakdown, context window state, session duration, and provider account limits. Sirvir-budget does NOT duplicate this — it complements it:

| Surface | Scope | What it answers |
|---------|-------|-----------------|
| `/usage` (native) | Current session | "What did this conversation cost?" |
| `audit_fleet.py` (Sirvir-budget) | All profiles, 30d windows | "What is the fleet spending? Which profiles dominate? What's the monthly projection?" |
| `verify_budget_docs.py` (Sirvir-budget) | Budget config validation | "Are the budget docs consistent and up to date?" |

When a user asks about spending, first suggest `/usage` for the immediate session answer. Then offer the fleet audit for the cross-profile, multi-day view. Sirvir-budget is the fleet-wide cost layer — `/usage` is the per-session cost layer.

## First-time setup: audit your fleet

Before using the budget skill, run the fleet audit to discover your profiles, their current models, and token usage:

```bash
python3 ${SIRVIR_SKILL_DIR}-budget/scripts/audit_fleet.py
```

This will:
1. Find all Hermes profiles under `${HERMES_HOME}/profiles/`
2. Read each profile's `config.yaml` to see what models they're using
3. Read each profile's `state.db` to aggregate token usage by model
4. Print a fleet-wide summary with cache rates and cost estimates
5. Identify which profiles are premium, default, or cheap tier based on their model choices

After the audit, edit `references/budget-config.yaml` to set your monthly budget and thresholds.

## When to use

Load this skill when any of the following are needed:

- The daily budget check is due (part of the 6:00 AM research cron)
- A user asks "what's my budget?", "how much have I spent?", "what's my projection?"
- A budget alert threshold (75% / 90% / 100%) was hit and needs surfacing
- An upgrade/downgrade suggestion is needed based on utilization
- A model swap's cost impact needs to be estimated before committing
- The user wants to change the monthly budget or alert thresholds
- Cache savings need to be reported (models with prompt caching)
- The user has a prepaid/GPU-time beta phase and a later token-billed production phase that need an apples-to-apples budget forecast
- The user expects post-upgrade caching improvements and needs a cache-aware effective-cost-per-million planning ladder

Trigger phrases: "what's my budget", "how much have I spent", "monthly projection", "budget alert", "cost tracking", "token usage", "cache savings", "can I afford <model>", "suggest a downgrade", "am I underutilizing".

## Data source: Hermes state.db

All usage data comes from Hermes's own SQLite database — real input/output/cache tokens, real cost, per model, per request. The database lives **per-profile**, not at `~/.hermes/state.db`. The correct path is:

```
${HERMES_HOME}/profiles/<profile_name>/state.db
```

For Sirvir's own profile: `${HERMES_PROFILE_DIR}/state.db`

> **Important**: The `sqlite3` CLI is NOT installed on this system. All queries must use Python's `sqlite3` module via `python3 -c "..."`. The queries below use this pattern.

### Quick schema check

```bash
# Check what tables exist and their schemas
python3 -c "
import sqlite3
db = sqlite3.connect('${HERMES_PROFILE_DIR}/state.db')
tables = db.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print('Tables:', [t[0] for t in tables])
for t in tables:
    cols = db.execute(f'PRAGMA table_info({t[0]})').fetchall()
    print(f'  {t[0]}: {[(c[1],c[2]) for c in cols]}')
"
```

### Standard queries (per-profile)

All queries use the `sessions` table — the `usage` table does not exist in this deployment. The `sessions` table has `input_tokens`, `output_tokens`, `cache_read_tokens`, `actual_cost_usd`, and `estimated_cost_usd`.

```bash
# Per-profile: this month's sessions by model
python3 -c "
import sqlite3
db = sqlite3.connect('${HERMES_PROFILE_DIR}/state.db')
db.row_factory = sqlite3.Row
rows = db.execute('''
SELECT COALESCE(model,'') AS model,
       COUNT(*) AS sessions,
       SUM(input_tokens) AS input_tok,
       SUM(output_tokens) AS output_tok,
       SUM(cache_read_tokens) AS cache_tok,
       ROUND(100.0 * SUM(cache_read_tokens) / NULLIF(SUM(input_tokens) + SUM(cache_read_tokens), 0), 2) AS cache_rate_pct,
       ROUND(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 2) AS cost_usd
FROM sessions
GROUP BY COALESCE(model,'')
ORDER BY (input_tok + output_tok + cache_tok) DESC
''').fetchall()
for r in rows:
    print(f'{r[\"model\"]:30s} sessions={r[\"sessions\"]:3d}  in={r[\"input_tok\"]:>10,}  out={r[\"output_tok\"]:>10,}  cache={r[\"cache_tok\"]:>10,}  rate={r[\"cache_rate_pct\"]:>6.1f}%  cost=\${r[\"cost_usd\"]:>8.2f}')
"
```

### Fleet-wide aggregate (all profiles)

```bash
# Aggregate across all profiles
python3 -c "
import sqlite3, os, glob
total_in = total_out = total_cache = 0
total_sessions = 0
for path in sorted(glob.glob('${HERMES_HOME}/profiles/*/state.db')):
    prof = path.split('/')[-2]
    db = sqlite3.connect(path)
    rows = db.execute('SELECT SUM(input_tokens), SUM(output_tokens), SUM(cache_read_tokens), COUNT(*) FROM sessions').fetchone()
    if rows[3]:
        total_in += rows[0] or 0
        total_out += rows[1] or 0
        total_cache += rows[2] or 0
        total_sessions += rows[3]
        print(f'{prof:20s}  sessions={rows[3]:3d}  in={rows[0] or 0:>12,}  out={rows[1] or 0:>10,}  cache={rows[2] or 0:>10,}')
print(f'{\"FLEET TOTAL\":20s}  sessions={total_sessions:3d}  in={total_in:>12,}  out={total_out:>10,}  cache={total_cache:>10,}')
total_tokens = total_in + total_out + total_cache
cache_rate = 100.0 * total_cache / (total_in + total_cache) if (total_in + total_cache) > 0 else 0
print(f'Total tokens: {total_tokens:,}')
print(f'Cache rate: {cache_rate:.1f}%')
"
```

### Effective cost during beta (subscription billing)

When the fleet runs on a subscription provider (ollama-cloud), per-token costs in state.db show $0. Compute effective cost from the subscription price divided by actual token volume:

```bash
# Effective cost per 1M tokens during beta
python3 -c "
import sqlite3, os, glob, yaml

# Read budget config
with open('${SIRVIR_SKILL_DIR}-budget/references/budget-config.yaml') as f:
    cfg = yaml.safe_load(f)

sub_cost = cfg['beta']['subscription_cost_usd']
period = cfg['beta']['billing_period']

# Fleet-wide token total
total_tokens = 0
for path in glob.glob('${HERMES_HOME}/profiles/*/state.db'):
    db = sqlite3.connect(path)
    row = db.execute('SELECT SUM(input_tokens + output_tokens + cache_read_tokens) FROM sessions').fetchone()
    if row[0]:
        total_tokens += row[0]

if total_tokens > 0 and sub_cost > 0:
    effective_per_1m = (sub_cost / total_tokens) * 1_000_000
    print(f'Subscription: \${sub_cost}/{period}')
    print(f'Total tokens: {total_tokens:,}')
    print(f'Effective cost: \${effective_per_1m:.4f} per 1M tokens')
else:
    print(f'Subscription cost unknown or zero tokens. Set beta.subscription_cost_usd in budget-config.yaml.')
"
```

## Budget config

The budget configuration lives at `references/budget-config.yaml` in the sirvir-budget skill directory. This is the **live source of truth** for the monthly budget, alert thresholds, scorecard anchors, planning bands, and beta/production tracking.

```bash
# Read the current budget
cat ${SIRVIR_SKILL_DIR}-budget/references/budget-config.yaml
```

Key fields:

| Field | Purpose |
|-------|---------|
| `monthly_budget_usd` | The user's monthly API budget |
| `alert_thresholds` | Yellow (75%), Orange (90%), Red (100%) of budget |
| `scorecard` | Operational thresholds for the weekly post-upgrade scorecard |
| `planning_bands` | Optimistic/base/conservative $/1M rates for cache-aware forecasting |
| `beta` | Beta period tracking (active, provider, subscription cost) |
| `production` | Post-beta provider and cutover date |

### Adjusting the budget

The user can change the budget at any time. Sirvir recalibrates projections and alerts against the new value.

```bash
# Edit the config directly
# Then re-run the budget check to confirm the new thresholds
python3 ${HERMES_PROFILE_DIR}/skills/turbofit/scripts/research-models.py
cat ${HERMES_PROFILE_DIR}/skills/turbofit/references/research-report.md
```

## Alert thresholds

| Threshold | Severity | Message template |
|-----------|----------|------------------|
| **75% of budget** | Yellow (WARN) | "You're trending toward your budget limit. Current projection: $X of $Y." |
| **90% of budget** | Orange (WARN) | "Budget nearly exhausted. Recommend switching to cheaper alternatives." |
| **100% of budget** | Red (CRITICAL) | "Budget exhausted. Switching to free endpoints only (NIM)." |

### Alert workflow

1. **Daily check** (6:00 AM research cron): compute month-to-date spend + projection
2. **Compare projection against thresholds**: if projected monthly spend crosses 75% / 90% / 100%, raise the corresponding alert
3. **Surface to Discord** (real-time for WARN/CRITICAL) and the consolidated log
4. **At 100%**: recommend switching to free NIM endpoints only — `serve auto main --free`

```bash
# Force a budget check on demand
python3 ${HERMES_PROFILE_DIR}/skills/turbofit/scripts/research-models.py
# The report includes a budget status section
grep -A 10 "Budget" ${HERMES_PROFILE_DIR}/skills/turbofit/references/research-report.md
```

## Over-budget suggestions

When spend is trending over budget, suggest specific swaps that save money. Always know the cost — these suggestions come from live pricing in `references/model-database.yaml` (kept current by sirvir-research).

| Situation | Suggestion template |
|-----------|---------------------|
| Premium main is the cost driver | "Switching main from GLM 5.2 ($0.95/$3.00) to DeepSeek V4 Pro (free via NIM) would save $X/month." |
| Aux usage is high | "Your aux usage is high. Routing more to the local MoE (free) would cut API costs by Y%." |
| Context bloat | "Consider reducing aux context to 512K — saves cache tokens without quality loss." |
| Pairing inefficiency | "Your current main+aux pairing costs $Z/M blended. Switching to <alt pair> costs $W/M — saves $V/month." |

## Underutilization suggestions

When spend is well under budget, suggest upgrades that improve quality without exceeding the budget.

| Situation | Suggestion template |
|-----------|---------------------|
| Low API spend | "You're only using 40% of your API budget. You could afford GLM 5.2 for main instead of DeepSeek V4 Flash — better quality for $X/month more." |
| Local GPU idle | "Your local GPU is underutilized. You could run a larger aux model (35B MoE) instead of the current 27B dense — same speed, more intelligence." |
| Context headroom | "You have headroom for a 1M context upgrade on main. Current: 262K. Cost: $0 additional (local)." |

## Cache-aware budget ladders and beta-vs-production comparisons

When the user is comparing:
- a prepaid or GPU-time-limited beta phase (for example Ollama subscription / GPU-time billing)
- against a later token-billed production phase

Do not compare the two phases with raw token totals alone.

Instead:
1. Treat beta as a workload-shape and caching-validation phase.
2. Convert production planning into an effective `$ / 1M tokens` rate.
3. Build an optimistic / base / conservative budget ladder from that effective rate.
4. Distinguish clearly between current measured cache performance and expected post-upgrade cache performance.

If the user provides small-scale and large-scale forecasts, test them for consistency by converting both to effective `$ / 1M` and comparing the band. If the bands are close, the forecast is directionally coherent.

Recommended planning shape for this class of case:
- planning anchor: base case
- stretch target: optimistic case
- do-not-be-surprised ceiling: conservative case

The session-derived reference ladder lives at `references/cache-aware-budget-ladder.md`.
For recurring weekly reviews after rollout, use `references/post-upgrade-budget-scorecard.md`.
For reconstructed or explained three-tier routing economics (premium / default / cheap lanes), use `references/lane-based-cost-model.md`.
For a full fleet cost spectrum analysis (per-profile, per-token, AS-IF deployed), see `references/cost-spectrum.md` — the canonical example of interview-driven cost modeling with baseline + stretch scenarios.
For comparing flat-rate subscription providers (Ollama Max/Pro) against per-token billing (Nous/OpenRouter), see `references/subscription-vs-per-token.md` — covers GPU-time estimation, request-count analysis, and tier-downgrade impact on subscription capacity.
For focused verification of budget-reference edits when no canonical test suite exists, run `scripts/verify_budget_docs.py` via a temporary `/tmp/hermes-verify-*` wrapper and report the result explicitly as ad-hoc verification rather than suite green.
For preparing sirvir-budget changes for an upstream PR to `example-user/sirvir`, see `references/upstream-contribution-workflow.md` — covers de-personalization, path normalization, and git workflow for fork-based PRs.
For usage-tier policy and fleet-audit changes, use `references/usage-tier-hardening-validation.md` plus the live validator at `${SIRVIR_SKILL_DIR}/scripts/validate_usage_tier.py` as the compliance checklist.

## Usage-tier hardening and compliance workflow

When editing `scripts/audit_fleet.py` or any coupled usage-tier routing logic in Sirvir, treat the work as a policy/compliance change, not a casual script tweak.

Required workflow:
1. Preserve additive layering: discovery -> deployed lane classification -> dominant 30d classification. Do not remove discovery or simplify away deployed/dominant outputs during cleanup.
2. Keep fleet semantics truthful: compute fleet from the full profile set first; if a CLI flag filters output to one profile, only the displayed subset changes, not the fleet rollup.
3. For sparse-evidence follow-up gating, the blocked path must return an error + followup question only. Do not leak `provisional_recommendation` or `recommendation_lanes` unless the caller explicitly opts into conservative fallback.
4. Validate overrides across separate invocations, not only with monkeypatched in-process helpers. Use env-overridable policy path and current timestamp so expiry/reversion is provable.
5. If provider/dashboard snapshot inputs are part of the policy, test them with a temporary policy + snapshot file and verify `snapshot_evidence` is surfaced in outputs.
6. Run both local verification and an independent second-agent audit before calling the change compliant.

Verification minimums for this class of change:
- `py_compile` on `audit_fleet.py`, `model_router.py`, and `validate_usage_tier.py`
- `python3 ${SIRVIR_SKILL_DIR}/scripts/validate_usage_tier.py`
- live blocked follow-up run that exits nonzero and hides recommendation fields
- live conservative-fallback run that succeeds
- live `audit_fleet.py --json` run confirming full-fleet rollup behavior

Pitfall: a validator that only checks exit code and `followup_required=true` is too weak. It must also assert that blocked follow-up output does not expose recommendation payloads.

## Beta provider substitution and budget tracking

When the fleet is running a beta period on ollama-cloud (substituting for Nous), budget tracking should note that:

- ollama-cloud costs are subscription-based (weekly quota, not per-token), so token cost in state.db may show $0 or a flat rate
- The real cost comparison ollama-cloud vs Nous should use the subscription cost divided by actual token volume
- When the beta ends and the fleet switches to Nous, per-token costs will appear in state.db
- Budget projections during beta should use the anticipated Nous pricing, not the current ollama-cloud $0

### Computing effective cost during beta

Since state.db shows $0.00 during subscription billing, compute effective cost manually:

```bash
# Effective cost per 1M tokens
python3 -c "
import sqlite3, glob, yaml

# Read budget config for subscription cost
with open('${SIRVIR_SKILL_DIR}-budget/references/budget-config.yaml') as f:
    cfg = yaml.safe_load(f)

sub_cost = cfg['beta']['subscription_cost_usd']
period = cfg['beta']['billing_period']

# Fleet-wide token total
total_tokens = 0
for path in glob.glob('${HERMES_HOME}/profiles/*/state.db'):
    db = sqlite3.connect(path)
    row = db.execute('SELECT SUM(input_tokens + output_tokens + cache_read_tokens) FROM sessions').fetchone()
    if row[0]:
        total_tokens += row[0]

if total_tokens > 0 and sub_cost > 0:
    effective_per_1m = (sub_cost / total_tokens) * 1_000_000
    print(f'Subscription: \${sub_cost}/{period}')
    print(f'Total tokens: {total_tokens:,}')
    print(f'Effective cost: \${effective_per_1m:.4f} per 1M tokens')
    # Compare against planning bands
    for band, rate in cfg['planning_bands'].items():
        status = 'BELOW' if effective_per_1m < rate else 'ABOVE'
        print(f'  vs {band} (\${rate}/1M): {status}')
else:
    print('Set beta.subscription_cost_usd in budget-config.yaml to enable effective-cost tracking.')
"
```

### Beta-to-production forecast

When the user asks for a production budget forecast during beta:

1. Read the current fleet-wide token volume from state.db
2. Read the production pricing from `model-database.yaml` for the planned post-cutover models
3. Apply the planning bands from `budget-config.yaml` (optimistic/base/conservative)
4. Present the forecast as a range, not a single number

```bash
# Production budget forecast from current beta usage
python3 -c "
import sqlite3, glob, yaml

# Fleet-wide token total
total_in = total_out = total_cache = 0
for path in glob.glob('${HERMES_HOME}/profiles/*/state.db'):
    db = sqlite3.connect(path)
    row = db.execute('SELECT SUM(input_tokens), SUM(output_tokens), SUM(cache_read_tokens) FROM sessions').fetchone()
    if row[0]:
        total_in += row[0] or 0
        total_out += row[1] or 0
        total_cache += row[2] or 0

total_tokens = total_in + total_out + total_cache

# Read planning bands
with open('${HERMES_PROFILE_DIR}/skills/turbofit/references/budget-config.yaml') as f:
    cfg = yaml.safe_load(f)

bands = cfg['planning_bands']
budget = cfg['monthly_budget_usd']

print(f'Current fleet volume: {total_tokens:,} tokens')
print(f'Monthly budget: \${budget}')
print()
print('Production forecast (post-beta, per-token billing):')
for label, rate in bands.items():
    monthly = (total_tokens / 1_000_000) * rate
    pct = (monthly / budget) * 100 if budget > 0 else 0
    print(f'  {label:15s} \${rate}/1M → \${monthly:.2f}/month ({pct:.0f}% of budget)')
"
```

## Daily budget check (part of 6:00 AM research cron)

The budget check is steps 2-5 and 9 of the daily research workflow (owned by sirvir-research):

1. **Read actual usage** from Hermes `state.db` (real tokens, cache hit rate, cost)
2. **Project monthly cost** for each model based on actual usage patterns
3. **Project pairing costs** with aux offset (40-85% of tokens route to aux)
4. **Report cache savings** for models that support cache reads
5. **Check budget status** — spend vs monthly budget, alert if threshold hit
6. (sirvir-research continues with HuggingFace scan, database update, GitHub sync)

```bash
# The research script does all of this; the budget section is in the report
python3 ${HERMES_PROFILE_DIR}/skills/turbofit/scripts/research-models.py

# Read just the budget-relevant sections
cat ${HERMES_PROFILE_DIR}/skills/turbofit/references/research-report.md | sed -n '/Budget/,/^##/p'
```

## On-demand budget report

When the user asks "what's my budget?" or "how much have I spent?":

```bash
# 1. Run the research script (fetches fresh pricing + reads state.db)
python3 ${HERMES_PROFILE_DIR}/skills/turbofit/scripts/research-models.py

# 2. Read the report
cat ${HERMES_PROFILE_DIR}/skills/turbofit/references/research-report.md

# 3. Quick fleet-wide aggregate
python3 -c "
import sqlite3, glob
total_in = total_out = total_cache = 0
for path in glob.glob('${HERMES_HOME}/profiles/*/state.db'):
    db = sqlite3.connect(path)
    row = db.execute('SELECT SUM(input_tokens), SUM(output_tokens), SUM(cache_read_tokens) FROM sessions').fetchone()
    if row[0]:
        total_in += row[0] or 0
        total_out += row[1] or 0
        total_cache += row[2] or 0
total = total_in + total_out + total_cache
cache_rate = 100.0 * total_cache / (total_in + total_cache) if (total_in + total_cache) > 0 else 0
print(f'Fleet total: {total:,} tokens, cache rate: {cache_rate:.1f}%')
"

# 4. Compare against budget
grep monthly_budget_usd ${HERMES_PROFILE_DIR}/skills/turbofit/references/budget-config.yaml
```

Present to the user:
```
Budget status: $X spent of $Y monthly (Z%)
Projection: $W by end of month (V% of budget)
Status: 🟢 green / 🟡 yellow (75%+) / 🟠 orange (90%+) / 🔴 red (100%+)
Top cost driver: <model> at $A/month
Cache savings: $B (C% of input tokens hit cache)
Suggestion: <upgrade or downgrade recommendation>
```

## Cost tracking philosophy

From AGENTS.md:

1. **Local models**: Zero API cost. VRAM and electricity are the only costs.
2. **API fallback**: Tracked via Hermes Insights (state.db) — real input/output/cache tokens, real cost.
3. **Monthly projection**: Based on actual usage patterns from Hermes state.db.
4. **Cache savings**: Reported for models that support prompt caching (78-99% savings on cache hits).
5. **Budget management**: Tracked against monthly budget with alerts at 75% / 90% / 100%.

**Prefer free endpoints.** Local → NIM free → paid API. Always know the cost.

## Integration with turbofit core

- **turbofit** owns the `scripts/research-models.py` script that reads `state.db` and generates the budget report, and the `references/budget-config.yaml` config file. This skill documents the budget workflow that sits on top of them.
- The daily research cron is registered in Sirvir's profile config; this skill is the budget-check portion of that cron.
- Pricing data used for cost projections comes from `references/model-database.yaml`, kept current by sirvir-research's OpenRouter sync.
- Budget-driven model swaps are executed via turbofit's `serve main`/`serve aux`/`serve auto main --free` commands.

## Cost Spectrum Analysis (interview-driven methodology)

When the user asks to "eval the cost spectrum" or "model out the cost on a token basis," do not jump straight to computation. Use an interview-driven methodology:

1. **Define criteria first.** State what a great result looks like — format, data sources, scenarios, verification method. Reference a past example (e.g. `turbofit/references/research-report.md`) as the format to match.
2. **Lock decisions one at a time.** Ask the user to verify each key assumption explicitly:
   - Which fleet state to model (AS-IF deployed vs current reality vs both)
   - Pricing source and cache-read rate assumptions
   - Token volume basis (current actuals vs forecast vs both)
   - Aux/compression token split methodology
   - Output format
3. **Compute from live data.** Read all state.db files, apply tier-assigned pricing, separate text from free aux (MiniMax M3 on NIM), compute effective $/1M rates.
4. **Include the root profile.** The root "default" profile's state.db lives at `${HERMES_STATE_DB}` — NOT under `${HERMES_HOME}/profiles/`. The `audit_fleet.py` script only scans `${HERMES_HOME}/profiles/*/state.db` and will miss the root profile. Always check `${HERMES_STATE_DB}` separately when doing fleet-wide analysis.
5. **Verify tier assignments.** Compare the policy-assigned tier against actual model usage in state.db. Flag mismatches explicitly.
6. **Delegate verification.** Use a subagent to check arithmetic, completeness, and threshold application before delivering.

The deliverable format: one markdown file with both scenarios (baseline + stretch), per-profile tables, fleet summary, tier breakdown, tier-assignment verification, cache gap analysis, scorecard assessment, and recommendations. See `references/cost-spectrum.md` for the canonical example.

### Pitfall: root profile at ${HERMES_STATE_DB}

The root "default" profile (the orchestrator) stores its state.db at `${HERMES_STATE_DB}`, not under `${HERMES_PROFILE_DIR}/default/state.db`. The `audit_fleet.py` script and the fleet-wide aggregate query both scan `${HERMES_HOME}/profiles/*/state.db` and will miss the root profile entirely. The root profile is typically the largest by token volume — missing it produces a materially wrong fleet analysis. Always check `${HERMES_STATE_DB}` separately.

### Pitfall: budget-config.yaml path

The budget config lives at `sirvir-budget/references/budget-config.yaml`, not `turbofit/references/budget-config.yaml`. Some older queries in this skill reference the turbofit path — use the sirvir-budget path for all budget operations.

### Pitfall: cache savings must use consistent prompt token bases

When computing "what if cache improved from X% to Y%," both scenarios must use the **same prompt token base** (input + cache_read). The error pattern: computing current cost on 611M prompt tokens (428M input + 183M cache) but target cost on 428M prompt tokens (86M input + 342M cache) — different bases produce a wrong savings number. Fix: lock the prompt token base first, then redistribute input/cache according to the target rate. For the root profile example: 611,389,576 prompt tokens × 30% cache = current; same 611,389,576 × 80% cache = target. The correct savings was $235.36/month, not $296.57.

### Pitfall: cache hit rate IS the cost driver on GPU-time/subscription providers

On flat-rate providers (ollama-cloud, Ollama Max/Pro), the billing unit is **GPU-time**, not tokens. A model with 0% cache hits burns GPU-time on every request recomputing the full context. A model with 25%+ cache hits reuses prefix computations and burns far less GPU-time per request.

**Diagnosing cache gaps — full workflow:**

Step 1: Check state.db for cache hit rates per model (fleet-wide):

```bash
python3 -c "
import sqlite3, glob, os
# Scan ALL state.db files including root and home profiles
state_dbs = []
for root in [os.environ.get('HERMES_HOME', str(Path.home() / '.hermes' / 'data')), os.environ.get('HERMES_HOME', str(Path.home() / '.hermes' / 'data')) + '/home']:
    for dirpath, dirnames, filenames in os.walk(root):
        if 'state.db' in filenames:
            state_dbs.append(os.path.join(dirpath, 'state.db'))
        if dirpath.count(os.sep) - root.count(os.sep) > 3:
            dirnames.clear()
for path in sorted(set(state_dbs)):
    db = sqlite3.connect(path)
    rows = db.execute('''
        SELECT COALESCE(model,''), COUNT(*),
               SUM(input_tokens), SUM(cache_read_tokens),
               ROUND(100.0 * SUM(cache_read_tokens) / NULLIF(SUM(input_tokens), 0), 1)
        FROM sessions GROUP BY model ORDER BY SUM(input_tokens) DESC
    ''').fetchall()
    if rows:
        prof = path.split('/')[-2] if '/profiles/' in path else 'root'
        print(f'=== {prof} ===')
        for r in rows:
            print(f'  {r[0]:30s} {r[1]:3d} sessions  {r[2] or 0:>12,} in  {r[3] or 0:>12,} cache  {r[4] or 0:>5.1f}%')
"
```

Step 2: Check API-level cache support — does the provider return `prompt_tokens_details` with `cached_tokens`?

```bash
# Test: back-to-back same prompt, check if prompt_tokens drops or cached_tokens appears
for i in 1 2; do
  curl -sL --max-time 30 "https://ollama.com/v1/chat/completions" \
    -H "Authorization: Bearer $OLLAMA_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"<model>","messages":[{"role":"system","content":"You are a test assistant."},{"role":"user","content":"Say hello"}],"max_tokens":20,"temperature":0}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); u=d.get('usage',{}); ptd=u.get('prompt_tokens_details',{}); print(f'prompt={u.get(\"prompt_tokens\")}, cached={ptd.get(\"cached_tokens\",\"NO DETAILS\")}')"
  sleep 2
done
```

Step 3: Cross-reference — if state.db shows cache hits but the API doesn't return `prompt_tokens_details`, the caching is happening at the Hermes level (system prompt prefix reuse across sessions), not at the provider API level.

**Known cache hit rates on ollama-cloud (2026-06-30):**

| Model | Cache Hit Rate | GPU-Time Impact |
|-------|---------------|-----------------|
| deepseek-v4-pro | **0%** | Maximum — every request recomputes full context |
| glm-5.2 | 24% | Moderate — ~1/4 of context reused |
| gpt-5.4 | 997% | Minimal — same prefix reused across sessions |

**Provider cache support matrix** — see `references/provider-cache-matrix.md` for the full cross-provider analysis.

A 0% cache model at 7M tokens/request burns GPU-time linearly with every turn. At 130 requests, that's ~900M tokens of GPU recomputation. A 24% cache model at the same volume saves ~216M tokens of GPU work. The dashboard "extra high usage" warning for deepseek-v4-pro is directly caused by the 0% cache rate — not by the model being inherently expensive.

**When the user reports high GPU-time burn on a subscription provider, check cache hit rate before recommending a model swap.** The fix may be enabling cache (if the provider supports it for that model) rather than switching models.

### Pitfall: spanning sessions inflate time-window queries

When querying state.db for a time window (e.g. "last 2 hours"), only count sessions where `started_at` falls within the window. Sessions that started earlier and are still running (`ended_at IS NULL` or `ended_at > window_start`) have **lifetime token totals** — their `input_tokens` and `output_tokens` cover the entire session, not just the window. Including them produces misleadingly large numbers.

Correct pattern:
```python
# Sessions STARTED in the window
cur.execute("SELECT ... FROM sessions WHERE started_at > ?", (window_start,))

# Do NOT use: WHERE ended_at > ? OR ended_at IS NULL
# That pulls lifetime totals from long-running sessions.
```

If the user asks for usage "in the last X hours" and the numbers look wrong, check whether spanning sessions were included. The dashboard is the authoritative source for actual GPU-time burn; state.db can only report session-level aggregates.

## Cross-references

- **sirvir-research** — owns the daily research cron and the OpenRouter pricing sync that keeps `model-database.yaml` pricing current; sirvir-budget's projections depend on that pricing data
- **sirvir-serve** — when a user wants an external app endpoint, sirvir-budget determines whether a paid API model fits the budget or a free/local option is the right call
- **sirvir-scale** — API fallback (Beefy Step 4+) has a cost; sirvir-budget tracks whether the fallback is free (NIM) or paid (Nous/OR), and a Step 7 fallback to paid API can trigger a budget alert
- **sirvir-bench** — benchmark scores justify upgrade/downgrade suggestions: a cheaper model that benchmarks within 5% of a premium one is a budget win
- **turbofit** (core skill) — `SKILL.md` documents the dynamic model database, the research script, and `serve auto main --free`; this skill is the cost-tracking workflow that sits on top of them
