---
name: sirvir-budget
description: "Token usage monitoring and budget skill. Documents how to read Hermes state.db for real usage data, track spending against a monthly budget, set alert thresholds (75% yellow, 90% orange, 100% red), and suggest upgrades/downgrades based on utilization. Complements the turbofit core skill — turbofit serves models, sirvir-budget tracks what they cost."
version: 1.0.0
author: SouthpawIN
license: MIT
tags: [budget, token-usage, cost-tracking, state-db, alerts, spending, turbofit]
metadata:
  hermes:
    tags: [budget, token-usage, cost-tracking, state-db, alerts, spending]
    related_skills: [turbofit, sirvir-research, sirvir-serve]
  changelog: |
    1.0.0 (2026-06-26): Initial split from turbofit monolith. Wraps the state.db usage queries, monthly budget tracking, alert thresholds, and upgrade/downgrade suggestion logic.
---

# Sirvir-Budget — Token Usage Monitoring & Budget

This skill is the **cost layer** of the Sirvir model fleet. The turbofit core skill serves models; sirvir-budget tracks what they actually cost — reading real usage from Hermes `state.db`, projecting monthly spend, alerting when thresholds are hit, and suggesting upgrades or downgrades based on utilization. The daily 6:00 AM research cron delegates the budget check to this workflow.

## When to use

Load this skill when any of the following are needed:

- The daily budget check is due (part of the 6:00 AM research cron)
- A user asks "what's my budget?", "how much have I spent?", "what's my projection?"
- A budget alert threshold (75% / 90% / 100%) was hit and needs surfacing
- An upgrade/downgrade suggestion is needed based on utilization
- A model swap's cost impact needs to be estimated before committing
- The user wants to change the monthly budget or alert thresholds
- Cache savings need to be reported (models with prompt caching)

Trigger phrases: "what's my budget", "how much have I spent", "monthly projection", "budget alert", "cost tracking", "token usage", "cache savings", "can I afford <model>", "suggest a downgrade", "am I underutilizing".

## Data source: Hermes state.db

All usage data comes from Hermes's own SQLite database — real input/output/cache tokens, real cost, per model, per request.

```bash
# Locate the database
ls -la ~/.hermes/state.db

# Quick check: is it a valid SQLite DB?
sqlite3 ~/.hermes/state.db ".tables"
```

### Standard queries

```bash
# Today's spend by model
sqlite3 -header -column ~/.hermes/state.db "
SELECT model,
       SUM(input_tokens)  AS input_tok,
       SUM(output_tokens) AS output_tok,
       SUM(cache_read_tokens) AS cache_tok,
       ROUND(SUM(cost), 4) AS cost_usd
FROM usage
WHERE date(timestamp) = date('now')
GROUP BY model
ORDER BY cost_usd DESC;
"

# This month's spend by model
sqlite3 -header -column ~/.hermes/state.db "
SELECT model,
       SUM(input_tokens)  AS input_tok,
       SUM(output_tokens) AS output_tok,
       SUM(cache_read_tokens) AS cache_tok,
       ROUND(SUM(cost), 2) AS cost_usd
FROM usage
WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
GROUP BY model
ORDER BY cost_usd DESC;
"

# Monthly projection (extrapolate current spend rate to end of month)
sqlite3 ~/.hermes/state.db "
WITH days_elapsed AS (
  SELECT CAST(strftime('%d', 'now') AS REAL) AS d
)
SELECT ROUND(
  (SELECT SUM(cost) FROM usage WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now'))
  / (SELECT d FROM days_elapsed)
  * CAST(strftime('%d', date('now', 'start of month', '+1 month', '-1 day')) AS REAL)
, 2) AS projected_monthly_usd;
"

# Cache savings (tokens that hit cache instead of full-price input)
sqlite3 -header -column ~/.hermes/state.db "
SELECT model,
       SUM(cache_read_tokens) AS cache_tok,
       ROUND(SUM(cache_read_tokens) * 0.000001 * (
         SELECT input FROM pricing WHERE model = usage.model LIMIT 1
       ), 2) AS estimated_savings_usd
FROM usage
WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
GROUP BY model
HAVING cache_tok > 0
ORDER BY estimated_savings_usd DESC;
"
```

> **Note on table/column names**: The exact schema of `state.db` may vary by Hermes version. Run `sqlite3 ~/.hermes/state.db ".schema usage"` to confirm column names before relying on a query. The queries above assume a `usage` table with `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cost`, and `timestamp` columns — adjust if the schema differs.

## Budget config

The budget configuration lives at `references/budget-config.yaml` in the turbofit skill directory.

```yaml
# references/budget-config.yaml
monthly_budget_usd: 50.00          # User-set monthly budget
currency: USD
cycle_day: 1                        # 1st of month default (reset day)
alert_thresholds:
  yellow: 0.75                      # 75% — trending toward limit
  orange: 0.90                      # 90% — nearly exhausted
  red: 1.00                         # 100% — exhausted, switch to free only
notes: "User adjustable — Sirvir recalibrates on change."
```

### Adjusting the budget

The user can change the budget at any time. Sirvir recalibrates projections and alerts against the new value.

```bash
# Edit the config directly (or use your editor of choice)
# Then re-run the budget check to confirm the new thresholds
python3 ~/.hermes/profiles/sirvir/skills/turbofit/scripts/research-models.py
cat ~/.hermes/profiles/sirvir/skills/turbofit/references/research-report.md
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
python3 ~/.hermes/profiles/sirvir/skills/turbofit/scripts/research-models.py
# The report includes a budget status section
grep -A 10 "Budget" ~/.hermes/profiles/sirvir/skills/turbofit/references/research-report.md
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
python3 ~/.hermes/profiles/sirvir/skills/turbofit/scripts/research-models.py

# Read just the budget-relevant sections
cat ~/.hermes/profiles/sirvir/skills/turbofit/references/research-report.md | sed -n '/Budget/,/^##/p'
```

## On-demand budget report

When the user asks "what's my budget?" or "how much have I spent?":

```bash
# 1. Run the research script (fetches fresh pricing + reads state.db)
python3 ~/.hermes/profiles/sirvir/skills/turbofit/scripts/research-models.py

# 2. Read the report
cat ~/.hermes/profiles/sirvir/skills/turbofit/references/research-report.md

# 3. Quick manual check of month-to-date spend
sqlite3 -header -column ~/.hermes/state.db "
SELECT ROUND(SUM(cost), 2) AS month_to_date_usd
FROM usage
WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now');
"

# 4. Compare against budget
grep monthly_budget_usd ~/.hermes/profiles/sirvir/skills/turbofit/references/budget-config.yaml
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

## Cross-references

- **sirvir-research** — owns the daily research cron and the OpenRouter pricing sync that keeps `model-database.yaml` pricing current; sirvir-budget's projections depend on that pricing data
- **sirvir-serve** — when a user wants an external app endpoint, sirvir-budget determines whether a paid API model fits the budget or a free/local option is the right call
- **sirvir-scale** — API fallback (Beefy Step 4+) has a cost; sirvir-budget tracks whether the fallback is free (NIM) or paid (Nous/OR), and a Step 7 fallback to paid API can trigger a budget alert
- **sirvir-bench** — benchmark scores justify upgrade/downgrade suggestions: a cheaper model that benchmarks within 5% of a premium one is a budget win
- **turbofit** (core skill) — `SKILL.md` documents the dynamic model database, the research script, and `serve auto main --free`; this skill is the cost-tracking workflow that sits on top of them
