---
name: sirvir-research
description: "Model research skill. Wraps HuggingFace scanning, OpenRouter pricing sync, and creator quality tracking. Documents how to scan HuggingFace for new GGUF models matching fleet archetypes, assess creator quality, update the model database, and sync to GitHub. Includes the creator quality database schema and the daily scan workflow. Complements the turbofit core skill — turbofit serves models, sirvir-research finds and vets them."
version: 1.0.0
author: SouthpawIN
license: MIT
tags: [huggingface, openrouter, model-discovery, creator-quality, research, pricing, github-sync, turbofit]
metadata:
  hermes:
    tags: [huggingface, openrouter, model-discovery, creator-quality, research, pricing, github-sync]
    related_skills: [turbofit, sirvir-bench, sirvir-budget]
  changelog: |
    1.0.0 (2026-06-26): Initial split from turbofit monolith. Wraps the daily research cron (research-models.py), HuggingFace scan workflow, creator quality database, and GitHub sync.
---

# Sirvir-Research — Model Discovery & Creator Intelligence

This skill is the **intake layer** of the Sirvir model fleet. The turbofit core skill serves what's already in the catalog; sirvir-research scans the horizon for what should enter it — new GGUF models on HuggingFace, live pricing on OpenRouter, and the track records of the creators behind them. It owns the daily 6:00 AM research sweep and the creator quality database.

## When to use

Load this skill when any of the following are needed:

- The daily research sweep is due (6:00 AM cron) — fetch live pricing, scan HuggingFace, update the database
- A specific HuggingFace scan is requested ("any new 27B models?", "what did unsloth release recently?")
- A new creator appeared and needs vetting — initial quality assessment
- An existing creator's track record needs updating after a new release
- Live OpenRouter pricing needs to be fetched and synced into `model-database.yaml`
- The model database needs to be synced to GitHub (`SouthpawIN/turbofit` + `SouthpawIN/sovth-config`)
- The user asks "what's new?" or "any good models dropped recently?"

Trigger phrases: "scan huggingface", "any new models", "research models", "fetch pricing", "update model database", "sync to github", "creator quality", "what did <creator> release", "daily research".

## Fleet archetypes (what to scan for)

Sirvir doesn't scan for *every* GGUF on HuggingFace — he scans for models matching the fleet's archetypes. A model outside these archetypes is noted but not pursued.

| Archetype | Typical Size (Q4) | VRAM | Current Fleet Model |
|-----------|-------------------|------|---------------------|
| 27-28B dense | 14-17 GB | ~22 GB | Darwin 28B Reason, Qwopus 27B |
| 35B MoE (3B active) | 11-17 GB | ~11-17 GB | Carnice 35A3B (Qwen3.6-35B-A3B) |
| 27B hybrid/Mamba | 14 GB | ~16 GB | Prism Eagle 27B |
| 35B MoE (3B active) — alt | 11-17 GB | ~11-17 GB | Darwin Apex |

Scan filters: GGUF format, file size in the 11-17 GB range (Q4_K_M), recent uploads (last 7 days by default), from known-good or new-but-promising creators.

## Daily research workflow (6:00 AM cron)

The daily sweep is the heartbeat of sirvir-research. It's implemented by `scripts/research-models.py` in the turbofit skill directory.

```bash
# Source the turbofit shim
source ~/.hermes/skills/turbofit/scripts/turbofit.sharco

# Run the daily research script (fetches pricing, scans HuggingFace, generates report)
python3 ~/.hermes/profiles/sirvir/skills/turbofit/scripts/research-models.py

# Read the generated report
cat ~/.hermes/profiles/sirvir/skills/turbofit/references/research-report.md
```

The script performs these steps in order:

1. **Fetch live pricing** from OpenRouter API (339+ models) — input/output/cache-read prices
2. **Read actual usage** from Hermes `state.db` (real tokens, cache hit rate, cost) — see sirvir-budget
3. **Project monthly cost** for each model based on actual usage patterns
4. **Project pairing costs** with aux offset (40-85% of tokens route to aux)
5. **Report cache savings** for models that support cache reads
6. **Scan HuggingFace** for new GGUF models matching fleet archetypes (see workflow below)
7. **Assess any new models found** — quick benchmark if time allows (delegates to sirvir-bench)
8. **Update creator quality database** with any new findings
9. **Check budget status** — spend vs monthly budget, alert if threshold hit (delegates to sirvir-budget)
10. **Update** `references/model-database.yaml` with new models or pricing changes
11. **Update** `references/creator-quality-database.yaml` with new assessments
12. **Sync to GitHub** — `SouthpawIN/turbofit` + `SouthpawIN/sovth-config`
13. **Post consolidated log** to Discord (daily summary) + blog (if noteworthy) + GitHub (structured data)

## HuggingFace scan workflow

### Step 1: Query the HuggingFace API

```bash
# Scan for recent GGUF uploads from known-good creators (last 7 days)
# The research script does this automatically; this is the manual escape hatch.

# Query HuggingFace API for new GGUF models from unsloth
curl -s "https://huggingface.co/api/models?author=unsloth&filter=gguf&sort=lastModified&direction=-1&limit=20" \
  | python3 -m json.tool | head -100

# Query for bartowski's recent GGUF uploads
curl -s "https://huggingface.co/api/models?author=bartowski&filter=gguf&sort=lastModified&direction=-1&limit=20" \
  | python3 -m json.tool | head -100

# General scan: recent GGUF uploads in the 27B size range
curl -s "https://huggingface.co/api/models?filter=gguf&sort=lastModified&direction=-1&limit=50" \
  | python3 -c "
import sys, json
models = json.load(sys.stdin)
for m in models:
    # Filter by likely 27-28B or 35B-A3B based on modelId naming
    mid = m.get('modelId', '')
    if any(k in mid.lower() for k in ['27b', '28b', '35b', 'a3b', 'qwen3']):
        print(f\"{mid}  (modified: {m.get('lastModified','?')})\")
"
```

### Step 2: Filter by known-good creators

Known-good creators get tested first (priority queue):

| Creator | Known For | Specialization | Notes |
|---------|-----------|-----------------|-------|
| unsloth | High-quality quantizations & fine-tunes | Dense models | Consistently good |
| bartowski | Prolific quantizer, wide coverage | All model classes | High volume, generally reliable |
| Ex0bit | Niche but high-quality work | Specialized models | Lower volume, careful work |
| I-Nano | Compact model specialist | Small models | Good for Modest/Thin tiers |
| I-Compact | Efficient model specialist | Compacted models | Good for VRAM-constrained setups |

New creators start with a **neutral score** and build reputation over time. A new creator with a promising upload gets tested; a known-bad creator gets tested last (or skipped if the backlog is full).

### Step 3: Download a sample quantization

Always Q4_K_M unless there's a reason to test a different quant.

```bash
# Download via turbofit (preferred — uses hf_repo from catalog if registered)
serve fetch <alias>

# Direct HuggingFace download (escape hatch)
# CRITICAL: use exact filenames, never wildcards — `*.gguf` downloads every quant (100-200 GB of junk)
hf download <repo> --include="*Q4_K_M*" --include="mmproj-F32.gguf" --local-dir <dest>

# Even safer: download only the one specific file
hf download <repo> --include="<exact-filename>.gguf" --local-dir <dest>
```

### Step 4: Benchmark against the current fleet model

Delegate to sirvir-bench. The new model is launched in its real serving configuration and evaluated on the standard suite (MMLU, GPQA, HumanEval, AIME; SWE-bench for main candidates).

```bash
# Register the new model temporarily for benchmarking
serve register <new-alias> /path/to/new-model-Q4_K_M.gguf --port 11540

# Benchmark it (sirvir-bench workflow)
serve bench <new-alias>

# Compare head-to-head with the current fleet occupant
serve bench compare_27b   # if it's a 27B-class model
```

### Step 5: Assess — upgrade, downgrade, or lateral?

- **Upgrade**: new model beats current on ≥3 of 5 benchmark tasks, with no regression >5% on any single task → recommend to user via Senter
- **Lateral**: within ±3% on all tasks → note for future reference (may become relevant if fleet needs change)
- **Downgrade**: worse on ≥3 of 5 tasks → reject, log to creator quality database

### Step 6: Log the assessment

- **Creator quality database**: `references/creator-quality-database.yaml` (structured)
- **Assessment journal**: `references/creator-assessments.md` (running log)
- **Consolidated log**: Discord + blog + GitHub (see AGENTS.md for the log format)

### Step 7: If upgrade → promote

```bash
# Register the new model permanently
serve register <new-alias> /path/to/model.gguf --port <port>

# Edit ~/.config/turbofit/models.yaml to add tier, presets, gpu, vision, role, etc.
# Then update references/model-database.yaml with the new entry

# Swap it in (after user approval)
serve main <new-alias> --ui tui
```

## Creator quality database schema

The creator quality database is a persistent, growing knowledge base. It lives at `references/creator-quality-database.yaml` in the turbofit skill directory and is synced to the `sovth-config` GitHub repo.

```yaml
# references/creator-quality-database.yaml
creators:
  unsloth:
    specialization: "Dense models"
    quality_score: 9          # 0-10 scale, weighted by benchmark results
    quantization_quality: 9   # Do their GGUFs quantize cleanly? Preserve intelligence?
    reliability: 9            # Consistently good, or hit-or-miss?
    latest_models:             # Recently released, kept current
      - "unsloth/Qwen3.6-27B-Darwin-Reason-GGUF"
      - "unsloth/Qwen3.6-35B-A3B-GGUF"
    track_record:             # Historical log of assessments
      - date: "2026-06-20"
        model: "Qwen3.6-27B-Darwin-Reason"
        assessment: "upgrade"
        benchmark_delta: "+4% MMLU, +6% HumanEval vs Qwopus 27B"
        notes: "Clean Q4_K_M, mmproj matched, no crashes"
      - date: "2026-06-15"
        model: "Qwen3.6-35B-A3B"
        assessment: "lateral"
        benchmark_delta: "within 2% on all tasks"
        notes: "MoE expert offload works cleanly with --cpu-moe-4"
    notes: "Consistently good. Priority-queue all new releases."

  bartowski:
    specialization: "All model classes"
    quality_score: 8
    quantization_quality: 8
    reliability: 8
    latest_models:
      - "bartowski/Qwen3.6-27B-Qwopus-27B-GGUF"
    track_record:
      - date: "2026-06-18"
        model: "Qwopus 27B"
        assessment: "lateral"
        benchmark_delta: "within 3% on all tasks"
        notes: "Prolific as always, reliable Q4_K_M"
    notes: "High volume, generally reliable. Test after unsloth."

  new-creator-example:
    specialization: "Unknown — first assessment"
    quality_score: 5          # Neutral starting score
    quantization_quality: 5
    reliability: 5
    latest_models:
      - "new-creator/SomeModel-27B-GGUF"
    track_record:
      - date: "2026-06-26"
        model: "SomeModel-27B"
        assessment: "pending"
        benchmark_delta: "not yet benchmarked"
        notes: "New creator, first upload. Queued for benchmarking."
    notes: "New creator. Build reputation over time."
```

### How creator quality influences decisions

- When two models are within ±2% on benchmarks, the **better-creator** wins
- When a known-good creator releases a new model, it gets tested **first** (priority queue)
- When a known-bad creator releases a model, it gets tested **last** (or skipped if backlog is full)
- A new creator starts neutral (5/10) and builds reputation with each assessment
- A single bad release doesn't tank a good creator's score — track record is weighted over volume

## OpenRouter pricing sync

Live pricing is fetched from the OpenRouter API and written into `references/model-database.yaml` under each model's `pricing:` block.

```bash
# Fetch all OpenRouter models with pricing (339+ models)
curl -s "https://openrouter.ai/api/v1/models" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for m in data.get('data', []):
    mid = m.get('id', '')
    pricing = m.get('pricing', {})
    ctx = m.get('context_length', '?')
    print(f'{mid}  prompt={pricing.get(\"prompt\",\"?\")}  completion={pricing.get(\"completion\",\"?\")}  ctx={ctx}')
" | head -50

# The research script does this automatically and merges into model-database.yaml
# Manual review: check references/research-report.md after the script runs
cat ~/.hermes/profiles/sirvir/skills/turbofit/references/research-report.md
```

The database schema for pricing (per model):

```yaml
pricing:
  nous: { input: 0.95, output: 3.00, slug: "z-ai/glm-5.2" }           # Through Nous gateway
  openrouter: { input: 0.95, output: 3.00, slug: "z-ai/glm-5.2", free: false, cache_read: 0.18 }
  nim: { input: 0, output: 0, slug: "deepseek-ai/deepseek-v4-pro" }   # NVIDIA NIM free
  direct: { input: 1.40, output: 4.40, provider: "Z.AI", cache_read: 0.26 }
```

## GitHub sync

The database and reference files are synced to two repos:

```bash
# Sync to GitHub (pushes to SouthpawIN/turbofit + SouthpawIN/sovth-config)
bash ~/.hermes/profiles/sirvir/skills/turbofit/scripts/sync-github.sh
```

- **`SouthpawIN/turbofit`** (primary) — the turbofit skill itself, including `references/model-database.yaml` and `references/creator-quality-database.yaml`
- **`SouthpawIN/sovth-config`** (collection) — broader config collection, includes database snapshots and raw log entries

**Rule**: Never create new GitHub repos or publish anything publicly without explicit user permission. Existing repos can be updated when the user directs work on them.

## Integration with turbofit core

- **turbofit** owns the catalog (`~/.config/turbofit/models.yaml`), the `serve fetch` command, and the `scripts/research-models.py` + `scripts/sync-github.sh` scripts that this skill documents.
- sirvir-research writes updates into `turbofit/references/model-database.yaml` and `turbofit/references/creator-quality-database.yaml` — turbofit is the source of truth for model metadata.
- The daily research cron is registered in Sirvir's profile config; this skill is the workflow that cron triggers.
- `serve recommend` reads benchmark scores and pricing from the database — so a sirvir-research pricing update influences the next `serve recommend` output.

## Cross-references

- **sirvir-bench** — owns the benchmarking workflow that evaluates models sirvir-research discovers; benchmark results feed back into the creator quality database
- **sirvir-budget** — owns the spend tracking that uses the pricing data sirvir-research fetches; budget alerts trigger when pricing changes push projection over threshold
- **sirvir-scale** — uses the archetype table (defined here) to pick scaling-ladder step targets
- **sirvir-serve** — uses creator quality scores when recommending models for external apps (a better-creator model wins ties)
- **turbofit** (core skill) — `SKILL.md` documents the dynamic model database, `serve fetch`, and the research scripts; this skill is the discovery workflow that sits on top of them
