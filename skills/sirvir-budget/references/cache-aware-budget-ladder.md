# Cache-aware Budget Ladder for Token-Based API Planning

Use this reference when the user has:
- a prepaid or GPU-time-limited beta phase
- a later token-billed production phase
- meaningful prompt caching improvements expected after a routing or provider upgrade

## Core rule

Do not compare beta and production with raw token totals alone when the billing models differ.

Instead:
1. Treat the beta as validation of workload shape and caching behavior.
2. Convert production planning to an **effective cost per 1M tokens**.
3. Build budget ladders from that effective rate, not from uncached headline pricing.

## Effective-rate method

If the user provides a forecast like:
- 80–90M tokens/week at about $10/week

Compute:
- $10 / 80M = $0.125 per 1M tokens
- $10 / 90M = $0.1111 per 1M tokens
- midpoint 85M/week = $0.1176 per 1M tokens

If the user also provides a scale-up forecast like:
- 4B tokens/month at about $526/month

Compute:
- $526 / 4,000M = $0.1315 per 1M tokens

If these effective rates are in the same band, the forecasts are directionally consistent.

## Recommended planning bands

For cache-improved production planning, use three bands. These are read from `turbofit/references/budget-config.yaml` under `planning_bands`:

```bash
python3 -c "
import yaml
with open('${HERMES_PROFILE_DIR}/skills/turbofit/references/budget-config.yaml') as f:
    cfg = yaml.safe_load(f)
bands = cfg['planning_bands']
for label, rate in bands.items():
    print(f'  {label}: \${rate} / 1M')
"
```

Current defaults:
- optimistic: $0.11 / 1M
- base: $0.125 / 1M
- conservative: $0.14 / 1M

These are not universal market prices. They are scenario-planning rates derived from the user's own forecasted post-cache workload. Update them in `budget-config.yaml` when the forecast changes.

## Budget ladder

### Monthly workload ladder

| Monthly tokens | Optimistic | Base | Conservative |
|---|---:|---:|---:|
| 100M | $11 | $12.50 | $14 |
| 500M | $55 | $62.50 | $70 |
| 1B | $110 | $125 | $140 |
| 2B | $220 | $250 | $280 |
| 4B | $440 | $500 | $560 |

### Weekly equivalent for 4B/month

| Scenario | Weekly | Daily |
|---|---:|---:|
| Optimistic | $102.67 | $14.67 |
| Base | $116.67 | $16.67 |
| Conservative | $130.67 | $18.67 |

## Simple rule of thumb

At these economics, every extra 100M tokens/month costs about:
- optimistic: $11
- base: $12.50
- conservative: $14

This is the fastest mental model for live budgeting.

## How to use with users

When the user says current caching is poor but expected to improve after an upgrade:
- do not anchor on current uncached or poorly cached spend
- present both the current observed cache share and the forecasted effective-rate ladder
- explicitly distinguish:
  - current measured cache performance
  - expected post-upgrade cache performance
  - full-scale future workload assumptions

## Interpretation guidance

- If a small-scale and large-scale forecast both imply roughly the same effective $/M band, the forecast is coherent.
- If a large-scale forecast implies dramatically lower $/M than the smaller-scale forecast, assume either very high cache reuse or an overly optimistic estimate and label that uncertainty clearly.
- For production planning, recommend a primary anchor near the base case and a ceiling near the conservative case.

## Suggested defaults for this class of case

- planning anchor: base case
- stretch target: optimistic case
- do-not-be-surprised ceiling: conservative case

Example:
- 4B/month workload
- planning anchor: about $500/month
- ceiling: about $560/month
- stretch target: about $440/month
