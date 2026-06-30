# Subscription vs Per-Token Provider Comparison

Use this reference when comparing flat-rate subscription providers (Ollama Max/Pro) against per-token billing (Nous, OpenRouter).

## When to use

- User asks "does it make sense using Ollama Max instead of per-token?"
- Evaluating whether a subscription plan can handle projected token volume
- Comparing GPU-time-based billing against token-based billing
- Modeling the impact of tier downgrades on subscription capacity

## Methodology

### 1. Get actual request counts by model

Ollama's usage dashboard shows request counts per model, not token counts. Use these to estimate GPU-time consumption:

```
GLM 5.2:        753 requests (54%)
DeepSeek V4 Pro: 521 requests (37%)
DeepSeek V4 Flash: 128 requests (9%)
```

### 2. Estimate relative GPU-time per request

Different models consume different amounts of GPU-time per request. Use conservative estimates:

| Model | GPU-time vs GLM 5.2 | Rationale |
|-------|-------------------|-----------|
| GLM 5.2 | 1.0× (baseline) | Heaviest model in fleet |
| DeepSeek V4 Pro | 0.60× | 1.6T MoE, 49B active — lighter than GLM |
| DeepSeek V4 Flash | 0.20× | 284B MoE, 13B active — lightest |

### 3. Compute total GPU units

```
GLM units = 753 × 1.0 = 753
DSv4Pro units = 521 × 0.60 = 313
Flash units = 128 × 0.20 = 26
Total = 1,091 GPU units
```

### 4. Infer plan limits from usage percentage

If the user reports "65.3% of Pro weekly limit used":
```
Pro weekly limit = 1,091 / 0.653 = 1,671 GPU units
Max weekly limit = 1,671 × 5 = 8,355 GPU units
```

### 5. Model tier-downgrade impact

Moving traffic from GLM 5.2 to DeepSeek V4 Pro reduces GPU-time per request. Estimate what fraction of GLM traffic moves:

```
Research stays on GLM (25% of GLM requests)
Root + example-maf-profile move to DSv4Pro (75% of GLM requests)

Post-downgrade:
  GLM units = 753 × 0.25 = 188
  DSv4Pro units = 313 + (753 × 0.75 × 0.60) = 651
  Flash units = 26
  Total = 865 GPU units (21% reduction)
```

### 6. Model aux offload impact

MiniMax M3 on NVIDIA NIM is free. If 40% of tokens route through free aux:
```
GPU units on ollama = 865 × 0.60 = 519
% of Max = 519 / 8,355 = 6%
```

### 7. Scale to target volume

```
Current weekly: 732M tokens
Target weekly (4B/month): 933M tokens
Scale factor: 1.27×

Scaled GPU units = 519 × 1.27 = 662
% of Max = 662 / 8,355 = 8%
```

### 8. Compare costs

```
Ollama Max: $100/month flat
Nous per-token: tokens × effective_rate
  = 4,000,000,000 / 1,000,000 × $0.1201
  = $480/month

Savings: $380/month (4.8× cheaper)
```

## Sensitivity analysis

Always test the worst case. If DSv4Pro is actually 70% of GLM's GPU cost instead of 60%:

```
Post-downgrade GPU units = 974
4B with aux = 745 units = 9% of Max
Still fits comfortably.
```

## Decision rule

- If projected GPU units < 50% of Max weekly limit: subscription is safe
- If 50-80%: monitor weekly, have fallback ready
- If >80%: subscription is too tight, prefer per-token or reduce volume

## Pitfalls

- **Ollama bills GPU-time, not tokens.** A lighter model (DSv4Pro) gives more tokens per GPU-second than a heavier one (GLM 5.2). Tier downgrades stretch subscription capacity.
- **Request counts ≠ token counts.** A single GLM 5.2 request may process 100K tokens while a Flash request processes 10K. The GPU-time model accounts for this — heavier models cost more GPU-time per request regardless of token count.
- **Aux offload is multiplicative.** Free MiniMax M3 on NIM reduces both token count AND GPU-time on the subscription provider. Model it as a percentage reduction on the final GPU units.
- **Pro limits are inferred, not documented.** Ollama doesn't publish exact GPU-unit limits. The inference from "X% of Pro used" is approximate. The 30-day test validates the inference.
