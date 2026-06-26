---
name: sirvir-bench
description: "Model benchmarking skill. Wraps `serve bench` and lm-eval-harness to run standardized benchmarks (MMLU, GPQA, SWE-bench, HumanEval, AIME) on local fleet models and monitored API models. Documents the benchmark workflow, score interpretation thresholds, and how benchmark results feed back into tier assignments in model-database.yaml. Complements the turbofit core skill — turbofit launches and serves models, sirvir-bench measures them."
version: 1.0.0
author: SouthpawIN
license: MIT
tags: [benchmarking, lm-eval, mmlu, gpqa, swe-bench, humaneval, aime, model-eval, turbofit]
metadata:
  hermes:
    tags: [benchmarking, lm-eval, mmlu, gpqa, swe-bench, humaneval, aime, model-eval]
    related_skills: [turbofit, sirvir-research, sirvir-scale]
  changelog: |
    1.0.0 (2026-06-26): Initial split from turbofit monolith. Wraps `serve bench`, lm-eval-harness workflow, score interpretation, and tier feedback loop.
---

# Sirvir-Bench — Model Benchmarking

This skill is the **measurement layer** of the Sirvir model fleet. The turbofit core skill launches and serves models; sirvir-bench runs the standardized evaluations that tell us *how smart* each model is, *how fast* it runs, and whether a new model earns a place in the catalog — and at which tier.

## When to use

Load this skill when any of the following are needed:

- A new local model was downloaded and needs evaluation before being promoted into the fleet catalog
- A weekly benchmark sweep is due (Sunday 2:00 AM cron)
- A head-to-head comparison between same-archetype models is requested (`serve bench compare_27b`)
- An API model's quality needs to be measured against the local fleet baseline
- A regression is suspected (a previously-good model now scoring lower — backend or quant change?)
- Tier assignments in `references/model-database.yaml` need revalidation with fresh scores
- The user asks "is model X actually better than model Y?" and benchmark data is the answer

Trigger phrases: "benchmark this model", "how smart is it", "run lm-eval", "compare 27B models", "is this an upgrade", "MMLU score", "regression check", "weekly benchmarks".

## Benchmark workflow

### 1. Launch the target model

The `serve bench` subcommand handles launching if the model isn't already running. It uses the same catalog entry, binary pin, and presets as a normal `serve <alias>` launch — so benchmarks reflect the *actual serving configuration*, not a synthetic one.

```bash
# Source the turbofit shim first (one-time, already in ~/.bashrc)
source ~/.hermes/skills/turbofit/scripts/turbofit.sharco

# Benchmark a registered catalog model (launches if needed, then runs lm-eval-harness)
serve bench darwin-28b-reason
serve bench carnice

# Head-to-head comparison of same-archetype models
serve bench compare_27b
```

### 2. What lm-eval-harness runs

The standard Sirvir benchmark suite covers these tasks:

| Task | What it measures | Why it matters |
|------|------------------|----------------|
| **MMLU** | Broad knowledge + reasoning (57 subjects) | General intelligence floor. A model below 0.70 MMLU is not fleet-worthy. |
| **GPQA** | Graduate-level science reasoning | Separates good reasoners from parrots. Diamond split is the canonical score. |
| **SWE-bench (Verified)** | End-to-end software engineering tasks | Real-world coding ability. The single best signal for a "coder main" model. |
| **HumanEval** | Python function synthesis | Quick coding floor. Cheap to run, correlates with SWE-bench. |
| **AIME** | Competition mathematics | Top-tier reasoning signal. AIME distinguishes the S-tier from the rest. |

Not every model runs every task — a fast aux model may skip SWE-bench. A 3B MoE aux may only get MMLU + HumanEval. The skill agent decides which suite applies based on the model's role (main gets the full suite; aux gets the quick set).

### 3. Running the suite manually (when `serve bench` is unavailable)

If the `serve bench` wrapper isn't available (broken shim, stale script), invoke lm-eval-harness directly against a running server. This is the escape hatch — `serve bench` is the preferred path.

```bash
# Prerequisite: the model must be launched and healthy
serve darwin-28b-reason
curl -s http://127.0.0.1:11500/v1/models | head   # confirm it's up

# Run MMLU against the running local server
lm_eval --model local-completions \
  --model_args "model=darwin-28b-reason,base_url=http://127.0.0.1:11500/v1/completions,num_concurrent=4" \
  --tasks mmlu \
  --batch_size 8 \
  --output_path ~/.hermes/profiles/sirvir/skills/turbofit/references/bench-results/darwin-28b-reason/$(date +%Y-%m-%d)

# Run HumanEval + GPQA Diamond
lm_eval --model local-completions \
  --model_args "model=darwin-28b-reason,base_url=http://127.0.0.1:11500/v1/completions,num_concurrent=4" \
  --tasks humaneval,gpqa_diamond \
  --batch_size 8 \
  --output_path ~/.hermes/profiles/sirvir/skills/turbofit/references/bench-results/darwin-28b-reason/$(date +%Y-%m-%d)

# AIME (competition math — fewer samples but high signal)
lm_eval --model local-completions \
  --model_args "model=darwin-28b-reason,base_url=http://127.0.0.1:11500/v1/completions,num_concurrent=2" \
  --tasks aime2024 \
  --batch_size 4 \
  --output_path ~/.hermes/profiles/sirvir/skills/turbofit/references/bench-results/darwin-28b-reason/$(date +%Y-%m-%d)
```

For SWE-bench Verified, the harness needs a Docker runtime and a separate evaluation container. Use the official runner:

```bash
# SWE-bench Verified (heavy — schedule for the weekly Sunday sweep, not on-demand)
lm_eval --model local-completions \
  --model_args "model=darwin-28b-reason,base_url=http://127.0.0.1:11500/v1/completions,num_concurrent=1" \
  --tasks swe_bench_verified \
  --output_path ~/.hermes/profiles/sirvir/skills/turbofit/references/bench-results/darwin-28b-reason/$(date +%Y-%m-%d)
```

### 4. Benchmarking API models (competitive intelligence)

API models don't need a local launch — point lm-eval-harness at the provider's endpoint directly.

```bash
# GLM 5.2 via Nous gateway (Tool Gateway active)
lm_eval --model local-completions \
  --model_args "model=z-ai/glm-5.2,base_url=https://api.nousresearch.com/v1/completions,num_concurrent=4" \
  --tasks mmlu,humaneval,gpqa_diamond,aime2024 \
  --batch_size 8 \
  --output_path ~/.hermes/profiles/sirvir/skills/turbofit/references/bench-results/glm-5.2/$(date +%Y-%m-%d)

# DeepSeek V4 Pro via free NIM endpoint
lm_eval --model local-completions \
  --model_args "model=deepseek-ai/deepseek-v4-pro,base_url=https://integrate.api.nvidia.com/v1/completions,num_concurrent=4" \
  --tasks mmlu,humaneval \
  --batch_size 8 \
  --output_path ~/.hermes/profiles/sirvir/skills/turbofit/references/bench-results/deepseek-v4-pro/$(date +%Y-%m-%d)
```

API models have rate limits — set `num_concurrent` conservatively and budget more wall-clock time. NIM free tier caps at ~1000 RPM.

## Score interpretation thresholds

Use these thresholds to decide whether a benchmark result is a pass, fail, or marginal. They are Sirvir's opinionated standards — a model that doesn't clear the bar for its archetype doesn't enter the fleet at tier `s`.

### Main model (27-28B dense or 35B MoE) — full suite

| Task | Tier `s` (smartest) | Tier `sf`/`sd` | Tier `f`/`c` | Fleet floor |
|------|---------------------|----------------|--------------|-------------|
| MMLU | ≥ 0.80 | ≥ 0.74 | ≥ 0.70 | 0.70 (below = reject) |
| GPQA Diamond | ≥ 0.45 | ≥ 0.35 | ≥ 0.28 | 0.25 |
| SWE-bench Verified | ≥ 0.35 | ≥ 0.25 | ≥ 0.15 | 0.10 |
| HumanEval | ≥ 0.80 | ≥ 0.72 | ≥ 0.65 | 0.60 |
| AIME 2024 | ≥ 0.30 | ≥ 0.15 | ≥ 0.05 | 0.00 (nice-to-have) |

### Aux model (35B MoE 3B-active or small dense) — quick set

| Task | Tier `sf` (smart+fast aux) | Tier `f` | Fleet floor |
|------|----------------------------|----------|-------------|
| MMLU | ≥ 0.72 | ≥ 0.68 | 0.65 |
| HumanEval | ≥ 0.68 | ≥ 0.60 | 0.55 |

Aux models are valued for speed and vision, not top-tier reasoning. AIME and SWE-bench are optional for aux.

### API models — competitive reference

API models are benchmarked against the same tasks but scored on a **competitive** curve — the question isn't "is this fleet-worthy" but "how does it compare to the local fleet and to other API options?"

| Tier | API model example | MMLU | Notes |
|------|-------------------|------|-------|
| S | GLM 5.2 | ~0.83 | Approaches Claude Opus 4.8 on terminal tasks |
| S | Qwen 3.7 MAX | ~0.82 | Flagship reasoning |
| S | DeepSeek V4 Pro | ~0.81 | 1.6T MoE, best open reasoning |
| SF | DeepSeek V4 Flash | ~0.76 | Free via NIM, strong for the price |

Record API benchmark scores in `references/model-database.yaml` under each model's `benchmarks:` block.

## How benchmark results feed back into tier assignments

This is the closed loop — sirvir-bench isn't just measurement, it *drives catalog decisions*.

### The feedback loop

1. **Benchmark completes** → results land in `references/bench-results/<model>/<date>/`
2. **Compare against the current fleet occupant of the same archetype** (see sirvir-research for the archetype table)
3. **Assess the delta:**
   - **Upgrade**: new model beats current on ≥3 of 5 tasks, with no regression >5% on any single task
   - **Lateral**: within ±3% on all tasks — note for future reference, no swap
   - **Downgrade**: worse on ≥3 of 5 tasks — reject, log to creator quality database
4. **If upgrade → update `references/model-database.yaml`:**
   - Set `benchmarks:` block with the new scores and source
   - Update `tier:` based on the thresholds above
   - Update `last_verified:` to today's date
5. **If the new model is entering the catalog → register it:**
   ```bash
   serve register <alias> /path/to/file.gguf --port <port>
   # Then edit ~/.config/turbofit/models.yaml to set tier, role, presets, vision, etc.
   ```
6. **Log the assessment** to the creator quality database (`references/creator-quality-database.yaml`) — see sirvir-research for the schema
7. **Post to the consolidated log** — Discord (alert if a swap is recommended), blog (weekly report), GitHub (structured data)

### Tier assignment rules

- A model's `tier` in the catalog (`s | sf | sd | f | c`) is **driven by benchmark scores**, not by reputation or size alone
- A known-good creator releasing a below-threshold model does **not** get a free pass — the thresholds are absolute
- A new creator clearing the `s` thresholds earns a `s` tier; reputation builds from there
- When two models are within ±2% on all tasks, the **better-creator** wins (see sirvir-research's creator quality database)
- Tier `s` is reserved — it's not a participation trophy. If no model clears the `s` bar in an archetype, the slot stays at `sf` until one does

## Weekly benchmark sweep (Sunday 2:00 AM)

This is the cron job that keeps the fleet honest. Run it during off-hours to minimize fleet impact.

```bash
# 1. Benchmark the current main model (all configured backends)
serve bench darwin-28b-reason

# 2. Benchmark the current aux model
serve bench carnice

# 3. Benchmark any new models added during the week
#    (iterate the catalog — anything with discovered: in the last 7 days)
serve bench <new-alias>

# 4. API model benchmarks (weekly competitive intelligence)
#    GLM 5.2, Qwen 3.7 MAX, DeepSeek V4 Pro/Flash, MiniMax M3, etc.
#    Use the API lm-eval commands above

# 5. Compare against previous benchmarks (detect regressions)
#    Look at references/bench-results/<model>/<previous-date>/ vs <today>/

# 6. Update backend performance database if a backend config changed
#    (see turbofit references/backend-performance.yaml)

# 7. Post weekly benchmark report to blog + Discord + GitHub
```

## Integration with turbofit core

- **turbofit** owns the catalog, launching, and serving. sirvir-bench depends on the catalog and `serve bench`/`serve <alias>` to launch models in their real serving configuration.
- Benchmark results are written under `turbofit/references/bench-results/` because that's where the model database and other reference data live — turbofit is the source of truth for model metadata.
- Tier updates from sirvir-bench flow back into `~/.config/turbofit/models.yaml` (the live catalog) and `turbofit/references/model-database.yaml` (the database snapshot).
- The daily research cron (`scripts/research-models.py`) reads benchmark scores from the database when ranking — so a sirvir-bench update influences the next day's `serve recommend` output.

## Cross-references

- **sirvir-research** — owns the HuggingFace scan that *finds* the models sirvir-bench evaluates, and the creator quality database that benchmark results feed back into
- **sirvir-scale** — uses tok/s measurements (a benchmark output) to decide scaling-ladder steps; a model that drops below 30 tok/s triggers a downscale
- **sirvir-serve** — uses tier assignments (set by sirvir-bench) when recommending models for external apps
- **sirvir-budget** — uses API model benchmark scores to justify upgrade/downgrade suggestions (a cheaper model that benchmarks within 5% of a premium one is a budget win)
- **turbofit** (core skill) — `SKILL.md` documents the catalog schema, `serve bench` command, and tier ladder; this skill is the measurement workflow that sits on top of it
