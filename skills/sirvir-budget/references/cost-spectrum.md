# Fleet Cost Spectrum — Post-7/4 Tier Routing

Date: 2026-06-29
Author: Sirvir
Status: Re-anchored after user corrections (v2)

## Purpose

Model the per-token cost of the fleet under the AS-IF deployed tier routing plan (post-7/4 cutover to Nous per-token billing). The budget anchor is **$550/month at 4B tokens** — target effective rate: $0.1375/1M. Two scenarios: current actual token volumes from state.db, and the 4B/month target. Verify what routing mix is required to hit the target.

## Data Sources

- **Token volumes**: Hermes state.db (9 profiles: root `${HERMES_STATE_DB}` + 8 per-profile `${HERMES_HOME}/profiles/*/state.db`)
- **Pricing**: `turbofit/references/model-database.yaml` — Nous gateway pricing with OpenRouter cache-read rates
- **Tier assignments**: `brain/0_Admin/fleet-routing-and-compression-policy-2026-06-28.md`
- **Budget**: $550/month at 4B tokens (user-confirmed 2026-06-29)

## Data Quality Caveats

### 1. MiniMax M3 Outage (NVIDIA provider)

MiniMax M3 on NVIDIA NIM was broken until ~12pm EST 2026-06-29. A patch was applied and initial benchmarks confirm it's working, but the state.db data was collected during the outage period. This means:

- **Aux share is artificially low.** Profiles that would normally offload vision/web_extract to free MiniMax M3 were forced to use text models instead.
- **Text token counts are overstated.** Some fraction of current text tokens would be free aux tokens under normal operation.
- **Cost projections are pessimistic.** The true post-cutover cost will be lower once MiniMax M3 is reliably handling vision/web_extract.

The aux % column below should be read as a floor, not a ceiling. Expect aux share to rise as MiniMax M3 stabilizes.

### 2. Ollama-Cloud Cache Reporting

Ollama-cloud does not accurately report cache-read tokens. The cache rates in state.db (28.2% fleet-wide) are unreliable during the beta period. All cache-dependent projections below are **directional only** — the true cache rate on Nous post-cutover may be materially different. Cache savings calculations use the state.db numbers as a working assumption, not ground truth.

### 3. Beta Provider Substitution

All profiles currently run on ollama-cloud (subscription billing, $0 cost in state.db). The cost model assumes the 7/4 cutover to Nous per-token billing has occurred. Current actual spend is $0.

## Pricing Basis (post-7/4)

| Model | Tier | Input $/1M | Output $/1M | Cache Read $/1M | Cache Savings |
|-------|------|-----------|------------|----------------|---------------|
| GLM 5.2 | Premium | $0.95 | $3.00 | $0.18 | 81% |
| DeepSeek V4 Pro | Default | $0.435 | $0.87 | $0.0036 | 99% |
| DeepSeek V4 Flash | Cheap | $0.09 | $0.18 | $0.02 | 78% |
| MiniMax M3 (NIM) | Aux (free) | $0.00 | $0.00 | $0.00 | N/A |

Cache-read rates assumed equivalent between Nous and OpenRouter gateways. MiniMax M3 (vision/web_extract) is free on NVIDIA NIM — excluded from cost calculations.

## Budget Anchor

| Metric | Value |
|--------|-------|
| Monthly budget | $550.00 |
| Target volume | 4,000,000,000 tokens/month |
| Target effective rate | **$0.1375/1M** |
| Baseline volume | 820,988,529 tokens |
| Baseline proportional budget | $112.89 |

The $550 budget is the 4B/month target, not the current-usage budget. The baseline's proportional share is $112.89 — the current $576.03 projection is 5.1× the proportional allowance.

## Methodology

1. For each profile, classify sessions into text (billable) and aux (free MiniMax M3) by model name
2. Apply tier-assigned model pricing to text tokens only
3. Compute effective $/1M rate = total cost / total text tokens × 1M
4. Cache rate = cache_read / (input + cache_read) — directional only (ollama-cloud caveat)
5. Aux % = MiniMax tokens / total tokens — floor only (MiniMax M3 outage caveat)
6. 4B/month target: scale all profile volumes proportionally from current actuals

## Scenario 1: Baseline (Current Actual Volumes)

### Per-Profile Cost

| Profile | Tier | Model | Text Tokens | Cache% | Aux% | Cost | $/1M |
|---------|------|-------|------------|--------|------|------|------|
| default | premium | glm-5.2 | 614,448,613 | 30.0% | 5.6% | $448.74 | $0.7303 |
| example-maf-profile | premium | glm-5.2 | 75,528,714 | 14.2% | 6.9% | $64.71 | $0.8568 |
| research | premium | glm-5.2 | 52,087,342 | 37.2% | 0.0% | $35.36 | $0.6789 |
| example-rollout-profile | default | deepseek-v4-pro | 46,733,734 | 18.2% | 0.7% | $16.85 | $0.3605 |
| sirvir | default | deepseek-v4-pro | 29,218,670 | 22.8% | 0.0% | $9.93 | $0.3398 |
| example-builds-profile | default | deepseek-v4-pro | 1,342,949 | 42.6% | 2.8% | $0.35 | $0.2586 |
| example-comms-profile | cheap | deepseek-v4-flash | 1,572,173 | 49.1% | 0.0% | $0.09 | $0.0572 |
| example-forge-profile | cheap | deepseek-v4-flash | 38,489 | 0.0% | 34.7% | $0.00 | $0.0907 |
| example-light-profile | cheap | deepseek-v4-flash | 17,845 | 0.0% | 50.7% | $0.00 | $0.0901 |

> **Aux % caveat**: The 0-7% aux shares on most profiles reflect the MiniMax M3 outage. Under normal operation, expect 20-40% of tokens to route through free aux, reducing text-token costs proportionally.

### Fleet Summary

| Metric | Value |
|--------|-------|
| Total text tokens | 820,988,529 |
| Fleet cache rate | 28.2% (directional only — ollama-cloud caveat) |
| Total cost | **$576.03** |
| Effective rate | $0.7016/1M |
| Target effective rate | $0.1375/1M |
| Gap | **5.1× too high** |
| Proportional budget (821M) | $112.89 |
| vs proportional | **510%** |

### Tier Breakdown

| Tier | Profiles | Text Tokens | Token Share | Cost | Cost Share |
|------|----------|------------|-------------|------|------------|
| Premium | 3 (default, example-maf-profile, research) | 742,064,669 | 90.4% | $548.81 | 95.3% |
| Default | 3 (example-rollout-profile, sirvir, example-builds-profile) | 77,295,353 | 9.4% | $27.13 | 4.7% |
| Cheap | 3 (example-comms-profile, example-forge-profile, example-light-profile) | 1,628,507 | 0.2% | $0.09 | 0.0% |

### Cost Concentration

The root "default" profile alone accounts for **$448.74 (77.9%)** of total fleet cost. It has 614M text tokens — 8× the next largest profile (example-maf-profile at 75M). Its cache rate (30.0%) is below the 80% target, meaning most of its GLM 5.2 input is uncached at full $0.95/1M.

## Scenario 2: 4B/Month Target

Scale factor: 4.87× from baseline (820,988,529 → 4,000,000,000)

### Per-Profile Cost at 4B/Month

| Profile | Tier | Text Tokens | Cost/Month |
|---------|------|------------|------------|
| default | premium | 2,993,701,330 | $2,186.34 |
| example-maf-profile | premium | 367,989,131 | $315.28 |
| research | premium | 253,778,659 | $172.28 |
| example-rollout-profile | default | 227,694,942 | $82.10 |
| sirvir | default | 142,358,481 | $48.38 |
| example-builds-profile | default | 6,543,082 | $1.71 |
| example-comms-profile | cheap | 7,659,902 | $0.44 |
| example-forge-profile | cheap | 187,525 | $0.00 |
| example-light-profile | cheap | 86,943 | $0.00 |
| **FLEET** | | **4,000,000,000** | **$2,806.52** |

### Stretch Summary

| Metric | Value |
|--------|-------|
| Total cost | **$2,806.52/month** |
| Effective rate | $0.7016/1M |
| Target effective rate | $0.1375/1M |
| Budget | $550.00 |
| Budget utilization | **510%** — 5× OVER |
| Premium share | 90.4% |

## Effective Rate by Cache Level

Since ollama-cloud cache is unreliable, here's what each model costs at different cache rates (assuming 0.55% output ratio, fleet average):

| Model | Cache 20% | Cache 40% | Cache 60% | Cache 80% |
|-------|----------|----------|----------|----------|
| GLM 5.2 | $0.8081 | $0.6550 | $0.5018 | $0.3487 |
| DeepSeek V4 Pro | $0.3516 | $0.2658 | $0.1800 | $0.0942 |
| DeepSeek V4 Flash | $0.0766 | $0.0626 | $0.0487 | $0.0348 |

**Key insight**: Even at 80% cache, GLM 5.2 costs $0.3487/1M — 2.5× the $0.1375 target. DeepSeek V4 Pro at 60% cache costs $0.1800/1M — still above target. Only DeepSeek V4 Flash at any cache level, or DeepSeek V4 Pro at 80%+ cache, fits under the target rate.

## Mix Scenarios to Hit $0.1375/1M

Assuming 60% cache (mid-range, achievable), 30% default share, and varying premium share:

| Premium Share | Default Share | Cheap Share | Blended $/1M | vs $0.1375 |
|--------------|--------------|-------------|-------------|------------|
| 5% | 30% | 65% | $0.1108 | ✓ UNDER |
| 10% | 30% | 60% | $0.1334 | ✓ UNDER |
| 15% | 30% | 55% | $0.1561 | ✗ OVER |
| 20% | 30% | 50% | $0.1787 | ✗ OVER |

**Finding**: At 60% cache, premium share must stay under ~12% to hit the $0.1375 target. The current 90.4% premium share is 7.5× too high.

### With MiniMax M3 Working (40% aux offload)

If 40% of total tokens route through free MiniMax M3 aux (plausible post-outage), the text-token budget relaxes:

| Metric | Value |
|--------|-------|
| Total tokens | 4,000,000,000 |
| Aux tokens (free) | 1,600,000,000 (40%) |
| Text tokens (billable) | 2,400,000,000 |
| Max effective rate on text | $0.2292/1M |

At $0.2292/1M, premium share can rise to ~25% at 60% cache — still far below the current 90.4%, but more breathing room than the no-aux scenario.

## Tier-Assignment Verification

### Policy vs Deployed Reality

| Profile | Policy Tier | Policy Model | Dominant Actual Model | Verdict |
|---------|------------|-------------|----------------------|---------|
| default | premium | glm-5.2 | glm-5 (150 sessions), gpt-5.4 (99) | **MISMATCH** — on glm-5/gpt-5.4 |
| example-maf-profile | premium | glm-5.2 | glm-5 (30), gpt-5.5 (6), glm-5.2 (3) | Partial |
| research | premium | glm-5.2 | gpt-5.4 (18), glm-5.2 (5) | Partial |
| example-rollout-profile | default | deepseek-v4-pro | deepseek-v4-pro (24), glm-5 (13) | Partial |
| sirvir | default | deepseek-v4-pro | gpt-5.4 (5), deepseek-v4-pro (2) | **MISMATCH** |
| example-builds-profile | default | deepseek-v4-pro | gpt-5.4 (4), deepseek-v4-pro (1) | **MISMATCH** |
| example-comms-profile | cheap | deepseek-v4-flash | gpt-5.4 (3), deepseek-v4-flash (2) | Partial |
| example-forge-profile | cheap | deepseek-v4-flash | gpt-5.4 (2) | **MISMATCH** |
| example-light-profile | cheap | deepseek-v4-flash | gpt-5.4 (1), minimax-m3 (1) | **MISMATCH** |

**5 of 9 profiles are still on gpt-5.4/grok-4.20, not their assigned tier models.** The cost model assumes the cutover has happened — actual current costs are $0 (beta subscription billing).

### Tier Appropriateness Check

| Profile | Text Tokens | Current Tier | Cost at Tier | Cost if Downgraded | Savings |
|---------|------------|-------------|-------------|-------------------|---------|
| default | 614M | premium ($448.74) | $448.74 | $267.29 (default) | $181.45 |
| example-maf-profile | 75M | premium ($64.71) | $64.71 | $32.85 (default) | $31.86 |
| research | 52M | premium ($35.36) | $35.36 | $22.66 (default) | $12.70 |
| example-rollout-profile | 46M | default ($16.85) | $16.85 | $4.21 (cheap) | $12.64 |
| sirvir | 29M | default ($9.93) | $9.93 | $2.63 (cheap) | $7.30 |

## Cache Performance Gap (Directional Only)

| Profile | Cache Rate | Target | Gap |
|---------|-----------|--------|-----|
| default | 30.0% | 80% | -50pp |
| example-maf-profile | 14.2% | 80% | -65.8pp |
| research | 37.2% | 80% | -42.8pp |
| example-rollout-profile | 18.2% | 80% | -61.8pp |
| sirvir | 22.8% | 80% | -57.2pp |
| example-builds-profile | 42.6% | 80% | -37.4pp |
| example-comms-profile | 49.1% | 80% | -30.9pp |
| Fleet avg | 28.2% | 80% | -51.8pp |

> **Caveat**: These cache rates come from ollama-cloud, which does not accurately report cache. The true post-cutover cache rate on Nous may be materially different. Treat these as a worst-case floor — Nous cache performance may be better.

At GLM 5.2 pricing, closing the cache gap from 30% to 80% on the root profile alone (assuming the state.db numbers are directionally correct):

- Current (30% cache): 428M input × $0.95 + 183M cache × $0.18 = $406.55 + $33.02 = $439.57
- At 80% cache: 122M input × $0.95 + 489M cache × $0.18 = $116.16 + $88.04 = $204.20
- **Savings: $235.36/month on the root profile alone**

## Executed Plan (2026-06-29)

All three levers pulled. Here's what was done and the new projected costs.

### Lever 1: Reduce Premium Share — EXECUTED

**Changes applied:**
- Root "default" profile: `model.default` changed from `deepseek-v4-flash` → `deepseek-v4-pro`; `aux.compression` from `glm-5.2` → `deepseek-v4-pro`
- example-maf-profile profile: `model.default` changed from `glm-5.2` → `deepseek-v4-pro`; `aux.compression` from `glm-5.2` → `deepseek-v4-pro`
- research: stays premium (glm-5.2) — only premium profile remaining

**New tier layout:**

| Tier | Profiles | Main Model | Compression |
|------|----------|-----------|-------------|
| Premium | research | glm-5.2 | glm-5.2 |
| Default | default, example-maf-profile, example-rollout-profile, sirvir, example-builds-profile | deepseek-v4-pro | deepseek-v4-pro |
| Cheap | example-comms-profile, example-forge-profile, example-light-profile | deepseek-v4-flash | deepseek-v4-flash |

**Three-layer alignment verified:**
- 9 profile config.yaml files: all verified OK
- model-routing SKILL.md: master + 7 profile copies synced
- provider_watchdog.py: master + 2 live copies synced (sha256 match)
- Fleet routing policy doc: updated

**New cost projection (Lever 1 only, 28% cache, 6% aux):**

| Scenario | Cost | $/1M | vs $550 Budget |
|----------|------|------|----------------|
| Baseline (821M) | $281.74 | $0.3432 | 51% of proportional ($112.89) |
| 4B scale | $1,372.68 | $0.3432 | 250% — still over |

### Lever 2: Cache Tracking — DEPLOYED

**Cron job created:** `cache-rate-tracker` (job_id: `4ba459740db9`)
- Runs daily at 6:00 AM
- Reads cache rates from all 9 profile state.db files
- Reports to Discord with GREEN/WARNING/CRITICAL status
- Flags ollama-cloud cache unreliability caveat

**Cache improvement strategy:**
- Standardize system prompts across profiles (reduce prompt churn)
- Increase session reuse (fewer fresh sessions = more cache hits)
- Target 60% cache rate post-cutover (current: 28%, directional only)
- Real cache measurement begins Week 1 on Nous (7/4+)

**New cost projection (Levers 1+2, 60% cache, 6% aux):**

| Scenario | Cost | $/1M | vs $550 Budget |
|----------|------|------|----------------|
| Baseline (821M) | $164.35 | $0.2002 | 30% of proportional ($112.89) |
| 4B scale | $800.73 | $0.2002 | 146% — still over |

### Lever 3: MiniMax M3 Aux — VERIFIED

**All 9 profiles confirmed:** vision and web_extract use `nvidia/minimaxai/minimax-m3` (free NIM). The NVIDIA provider bug was patched at 12pm EST 2026-06-29. Initial benchmarks confirm it's working.

**Expected impact:** 20-40% of tokens should offload to free aux once MiniMax M3 is stable. Current aux share (6%) is artificially low due to the outage.

**New cost projection (Levers 1+2+3, 60% cache, 40% aux):**

| Scenario | Cost | $/1M | vs $550 Budget |
|----------|------|------|----------------|
| Baseline (821M) | $98.61 | $0.1201 | 18% of proportional ($112.89) |
| 4B scale | **$480.44** | $0.1201 | **87% — UNDER BUDGET** |

### Remaining Unknowns

1. **Ollama Max weekly limits.** Pro weekly limit inferred at 146M GPU units. Max at 5× = 731M. Post-downgrade + aux offload projects 662 GPU units/week at 4B scale — 8% of Max. But this is inferred from Pro usage, not measured on Max. The 30-day test will confirm.
2. **MiniMax M3 stability.** The patch is fresh. If it degrades, aux share drops and GPU-time on ollama-cloud rises.
3. **Quality impact of tier downgrade.** Root and example-maf-profile are now on DeepSeek V4 Pro instead of GLM 5.2. If quality degrades on critical tasks, use premium escalation routing.

### Ollama Max vs Nous Per-Token

| | Ollama Max | Nous Per-Token (post-levers) |
|---|---|---|
| Monthly cost | **$100 flat** | $480 at 4B |
| Billing | GPU-time, not tokens | Per-token |
| Effective $/1M | $0.0319 | $0.1201 |
| Headroom at 4B | 92% unused | N/A (unlimited) |
| Risk | Limits may tighten | Cache may be worse than assumed |

**Decision:** 30-day Ollama Max test starting 7/4. Evaluate at end of July. Fallback to Nous if Max limits are hit.

### Monitoring

- **Daily:** cache-rate-tracker cron (6:00 AM, Discord)
- **Weekly:** Ollama usage dashboard (% of Max limit, GPU units consumed)
- **Weekly:** post-upgrade scorecard (spend, effective rate, premium share)
- **7/4:** upgrade to Ollama Max plan. No config changes needed — provider stays ollama-cloud.
- **8/4:** decision point. Stay on Max or switch to Nous per-token.
