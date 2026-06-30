# Post-upgrade Budget Scorecard

Use this reference for recurring weekly budget reviews after a routing, provider, or caching upgrade.

This scorecard is designed for cases where:
- current cache behavior is poor or unknown
- the target post-upgrade cache performance is materially better
- the user needs green/yellow/red operational thresholds rather than one-off estimates

## Threshold source of truth

All scorecard thresholds are defined in `turbofit/references/budget-config.yaml` under the `scorecard` key. This document describes the methodology; the live numbers come from the config.

```bash
# Read current scorecard thresholds
python3 -c "
import yaml
with open('${HERMES_PROFILE_DIR}/skills/turbofit/references/budget-config.yaml') as f:
    cfg = yaml.safe_load(f)
sc = cfg['scorecard']
print('Spend thresholds:')
print(f'  Green:  < \${sc[\"spend_green\"]}')
print(f'  Yellow: < \${sc[\"spend_yellow\"]}')
print(f'  Orange: < \${sc[\"spend_orange\"]}')
print(f'  Red:    > \${sc[\"spend_red\"]}')
print()
print('Effective rate thresholds (\$/1M):')
print(f'  Green:  < \${sc[\"effective_rate_green\"]}')
print(f'  Yellow: < \${sc[\"effective_rate_yellow\"]}')
print(f'  Orange: < \${sc[\"effective_rate_orange\"]}')
print(f'  Red:    > \${sc[\"effective_rate_red\"]}')
print()
print('Premium share thresholds:')
print(f'  Green:  < {sc[\"premium_share_green\"]*100:.0f}%')
print(f'  Yellow: < {sc[\"premium_share_yellow\"]*100:.0f}%')
print(f'  Orange: < {sc[\"premium_share_orange\"]*100:.0f}%')
print(f'  Red:    > {sc[\"premium_share_red\"]*100:.0f}%')
print()
print('Cache rate thresholds:')
print(f'  Green:  > {sc[\"cache_rate_green\"]*100:.0f}%')
print(f'  Yellow: > {sc[\"cache_rate_yellow\"]*100:.0f}%')
print(f'  Orange: > {sc[\"cache_rate_orange\"]*100:.0f}%')
print(f'  Red:    < {sc[\"cache_rate_red\"]*100:.0f}%')
print()
print(f'Monthly budget: \${cfg[\"monthly_budget_usd\"]}')
"
```

## Core rule

If provider-side cache telemetry is incomplete, treat `effective $ / 1M tokens` as the primary truth metric.

That metric absorbs:
- cache performance
- routing mix
- output pressure
- prompt reuse quality

## Planning anchors

Planning anchors are read from `budget-config.yaml`:
- `monthly_budget_usd` — the working monthly budget anchor
- `planning_bands.base` — expected normal band
- `planning_bands.optimistic` — good outcome
- `planning_bands.conservative` — caution zone

The scorecard thresholds (`scorecard.spend_*`) provide the operational guardrails.

## Core KPIs

Track these every week:
1. Total token volume
   - input tokens
   - output tokens
   - cache-read tokens, if visible
   - total effective tokens processed
2. Effective cost
   - spend this week
   - month-to-date spend
   - projected monthly spend
   - effective $ / 1M tokens
3. Routing mix
   - premium-tier share
   - default-tier share
   - cheap-tier share
4. Cache performance
   - true cache rate, if available
   - otherwise a proxy judgment from effective $ / 1M and prompt reuse stability
5. Output pressure
   - output/input ratio

## Status thresholds

All threshold values are read from `budget-config.yaml` at check time. The values below are the current defaults; they change when the user updates the config.

### 1. Monthly spend projection

| Status | Threshold (from config) |
|--------|-------------------------|
| Green | under `scorecard.spend_green` |
| Yellow | `scorecard.spend_green` to `scorecard.spend_yellow` |
| Orange | `scorecard.spend_yellow` to `scorecard.spend_orange` |
| Red | above `scorecard.spend_red` |

### 2. Effective cost per 1M tokens

| Status | Threshold (from config) |
|--------|-------------------------|
| Green | under `scorecard.effective_rate_green` |
| Yellow | `scorecard.effective_rate_green` to `scorecard.effective_rate_yellow` |
| Orange | `scorecard.effective_rate_yellow` to `scorecard.effective_rate_orange` |
| Red | above `scorecard.effective_rate_red` |

Interpretation:
- Green means the upgrade is delivering strong economics.
- Yellow means performance is roughly in the expected planning band.
- Orange means economics are degrading and should be reviewed.
- Red means routing, prompt structure, or caching behavior needs intervention.

### 3. Premium-tier share

| Status | Threshold (from config) |
|--------|-------------------------|
| Green | under `scorecard.premium_share_green` |
| Yellow | `scorecard.premium_share_green` to `scorecard.premium_share_yellow` |
| Orange | `scorecard.premium_share_yellow` to `scorecard.premium_share_orange` |
| Red | above `scorecard.premium_share_red` |

Interpretation:
- If premium share rises too high, cost will drift toward the upper forecast band even if caching is decent.
- The three-tier model means "premium share" = fraction of traffic hitting GLM 5.2, not DeepSeek V4 Pro or Flash.

### 4. Cache performance target

If the provider exposes true cache rate:

| Status | Threshold (from config) |
|--------|-------------------------|
| Green | above `scorecard.cache_rate_green` |
| Yellow | `scorecard.cache_rate_green` to `scorecard.cache_rate_yellow` |
| Orange | `scorecard.cache_rate_yellow` to `scorecard.cache_rate_orange` |
| Red | under `scorecard.cache_rate_red` |

If the provider does not expose true cache rate:
- infer a cache-performance proxy from effective $ / 1M and stable prompt reuse behavior
- use the effective-cost thresholds above as the stronger signal

## Weekly checkpoint template

```text
Week ending:
- spend this week: $__
- month-to-date spend: $__
- projected monthly spend: $__
- total tokens this week: __
- effective $/1M this week: $__
- premium share: __%
- default share: __%
- cheap share: __%
- cache rate / proxy: __%
- output/input ratio: __

Status lights
- budget: green / yellow / orange / red
- effective rate: green / yellow / orange / red
- routing mix: green / yellow / orange / red
- cache performance: green / yellow / orange / red

Weekly judgment
- overall status: healthy / watch / intervene
- top cost driver: __
- likely cause: routing / cache reuse / output bloat / prompt churn / other
```

## Decision rules

### If projected monthly spend is above `scorecard.spend_orange`
- review premium share immediately
- move more borderline workflows to the default or cheap tier
- inspect whether high-volume admin, example-comms-profile, example-light-profile, or coordination work is accidentally using the premium tier

### If projected monthly spend is above `scorecard.spend_red`
- perform a hard review of all premium defaults
- inspect the top three highest-volume workflows
- reduce unnecessary repeated long-context input
- tighten default/cheap routing for lower-stakes tasks

### If effective cost is above `scorecard.effective_rate_orange`
- inspect cache behavior
- inspect whether contexts are being resent too often
- inspect prompt stability and session reuse
- inspect whether output volume is creeping upward

### If effective cost is above `scorecard.effective_rate_red`
- intervene that week; do not wait for month-end
- assume one or more of these is true:
  - cache reuse is weaker than expected
  - premium routing is too high
  - too much fresh long-context input is being sent
  - output generation is too large relative to input

### If premium share is above `scorecard.premium_share_yellow`
- verify whether the workload truly requires premium quality
- move lower-stakes or repetitive workflows to the default or cheap tier where safe

### If premium share is above `scorecard.premium_share_orange`
- assume cost pressure will remain elevated
- only accept this state intentionally for research-heavy or high-stakes work months

### If cache performance is below `scorecard.cache_rate_yellow`
- inspect prompt architecture
- standardize system prompts where possible
- reduce avoidable prompt churn
- increase reuse of stable long-lived contexts
- check whether sessions are being restarted too often

### If cache performance is below `scorecard.cache_rate_orange`
- treat it as a routing and prompt-design issue, not only a cost issue
- prioritize optimization work that week

## Suggested operating targets

### Excellent month
- spend below `scorecard.spend_green`
- effective cost below `scorecard.effective_rate_green`
- premium share below `scorecard.premium_share_green` without harming quality
- cache telemetry or proxy looks strong and stable

### Acceptable month
- spend between `scorecard.spend_yellow` and `scorecard.spend_orange`
- effective cost between `scorecard.effective_rate_yellow` and `scorecard.effective_rate_orange`
- premium share between `scorecard.premium_share_green` and `scorecard.premium_share_yellow`
- cache behavior improved materially from pre-upgrade state

### Bad month
- spend above `scorecard.spend_red`
- effective cost above `scorecard.effective_rate_red`
- premium share above `scorecard.premium_share_orange` or cache performance clearly weak

## Scorecard rubric

Assign each category a score:
- Green = 3
- Yellow = 2
- Orange = 1
- Red = 0

Categories:
- budget projection
- effective cost
- premium share
- cache performance

Total score interpretation:
- 10-12 = healthy
- 7-9 = watch
- 4-6 = intervene
- 0-3 = immediate routing/prompt correction

## Recommended first-month alert thresholds

For the first post-upgrade month, the alert thresholds come from `budget-config.yaml`:

Budget alerts (from `alert_thresholds` × `monthly_budget_usd`):
- Yellow: projected monthly spend above `monthly_budget_usd × alert_thresholds.yellow`
- Orange: projected monthly spend above `monthly_budget_usd × alert_thresholds.orange`
- Red: projected monthly spend above `monthly_budget_usd × alert_thresholds.red`

Effective-cost alerts (from `scorecard`):
- Yellow: effective cost above `scorecard.effective_rate_yellow`
- Orange: effective cost above `scorecard.effective_rate_orange`
- Red: effective cost above `scorecard.effective_rate_red`

## How to present the result to the user

Use this compact structure:

```text
Budget status: <green|yellow|orange|red>
Projection: $X/month
Effective rate: $Y per 1M
Premium share: Z%
Cache status: <measured or proxy>
Top cost driver: <workflow/model/profile>
Action: <stay the course | watch | intervene>
```

## Notes

- This scorecard is meant for recurring operational reviews, not one-off pricing answers.
- When provider cache telemetry is unavailable or ambiguous, the final arbiter is the effective cost per 1M tokens.
- Update `budget-config.yaml` (not this document) when thresholds need to change. This document reads from the config.
- The three-tier model (premium/default/cheap) means "premium share" tracks GLM 5.2 usage specifically, not all non-free traffic.
