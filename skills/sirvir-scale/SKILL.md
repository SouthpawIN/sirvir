---
name: sirvir-scale
description: "VRAM scaling skill. Wraps `serve vram`, `serve downscale`, and the scaling ladder. Documents the 3-tier (Beefy/Modest/Thin) hardware detection, the 7-step Beefy scaling ladder, the Modest (5-step) and Thin (4-step) ladders, when to trigger downscale, and how to recover when VRAM frees up. Includes the optimization priority ladder (262K → 30 tok/s → 1M → max speed). Complements the turbofit core skill — turbofit launches models, sirvir-scale adapts them to live conditions."
version: 1.0.0
author: SouthpawIN
license: MIT
tags: [vram, scaling, gpu, downscale, beefy, modest, thin, scaling-ladder, turbofit]
metadata:
  hermes:
    tags: [vram, scaling, gpu, downscale, beefy, modest, thin, scaling-ladder]
    related_skills: [turbofit, sirvir-bench, sirvir-serve]
  changelog: |
    1.0.0 (2026-06-26): Initial split from turbofit monolith. Wraps `serve vram`, `serve downscale`, the 3-tier detection, all three scaling ladders, and the optimization priority ladder.
---

# Sirvir-Scale — VRAM Scaling & Adaptation

This skill is the **adaptation layer** of the Sirvir model fleet. The turbofit core skill launches models in their ideal configuration; sirvir-scale watches VRAM pressure and walks them down (or back up) the scaling ladder so the fleet always has *good intelligence available*, no matter what hardware is present or how loaded it is.

## When to use

Load this skill when any of the following are needed:

- Live VRAM state needs checking (`serve vram`)
- VRAM pressure is suspected (slow responses, OOM errors, another process grabbed GPU memory)
- The scaling ladder needs to be walked down (`serve downscale`)
- VRAM has freed up and the fleet should scale back up to the ideal step
- A hardware change occurred (GPU added/removed, VRAM changed) and the tier needs re-detection
- The 4-hourly scaling-check cron is due
- A user asks "why is my model slow?" or "can I fit a bigger model?"
- The optimization priority (262K → 30 tok/s → 1M → max speed) needs to be applied to a config decision

Trigger phrases: "check vram", "scale down", "downscale", "vrarm pressure", "gpu is busy", "free up memory", "scale back up", "what tier am I", "optimization priority", "why is it slow".

## Optimization priority ladder (the golden rule)

Before any scaling decision, internalize this priority order. It applies to backend selection, config tuning, and model selection equally.

| Priority | Target | Rationale |
|----------|--------|----------|
| 1 | **262K context length** | Minimum viable for productive use. Below this, not usable for real work. |
| 2 | **30 tok/s** | Minimum viable speed for interactive use. Below this, too slow for real-time. |
| 3 | **1M context length** | Stretch goal. Unlocks long-form work (codebases, documents, multi-turn). |
| 4 | **Max speed** | Once all above are met, maximize tok/s for fleet responsiveness. |

**The ladder is: 262K → 30 tok/s → 1M → max speed.**

Rules:
- Never trade context for speed unless 262K is achieved.
- Never trade 30 tok/s for more context unless 30 tok/s is achieved.
- A scaling step that drops below 262K ctx or 30 tok/s is only acceptable at Step 6+ (extreme/API-only) — below those floors, the model isn't usable for real work and API fallback is the right answer.

## Hardware tier detection (3 tiers)

`serve auto` probes `nvidia-smi` and auto-detects which tier applies. If no NVIDIA GPU is found, it defaults to **Thin** (API-only).

```bash
# Source the turbofit shim
source ~/.hermes/skills/turbofit/scripts/turbofit.sharco

# Let turbofit detect your hardware and pick the best setup
serve auto main

# Force API-only mode (no local GPU needed)
serve auto main --api

# Force free-only endpoints (zero cost)
serve auto main --free
```

| Tier | Total VRAM | Typical GPUs | Strategy |
|------|-----------|-------------|----------|
| **Beefy** | ≥24GB | 2× RTX 3090/4090, or single 24GB+ | Local main + local aux |
| **Modest** | 8-24GB | RTX 3060/4060 (12GB), RTX 3070/4070 (8-16GB) | API main + local or API aux |
| **Thin** | <8GB or no NVIDIA GPU | Integrated graphics, GT 1030, no GPU | API main + API aux |

The Sirvir fleet (per AGENTS.md hardware context) runs on a **Beefy** tier: dual GPU, ≥24GB VRAM per GPU. The Beefy ladder below is the primary workflow; Modest and Thin are documented for completeness and for cross-tier escalation.

## Live VRAM probe

Always probe before acting. This is Sirvir's first convention.

```bash
# Live GPU VRAM probe (JSON output)
serve vram

# Example output:
# {
#   "gpus": [
#     { "index": 0, "name": "NVIDIA GeForce RTX 3090", "total_mb": 24576, "used_mb": 17800, "free_mb": 6776 },
#     { "index": 1, "name": "NVIDIA GeForce RTX 3090", "total_mb": 24576, "used_mb": 15200, "free_mb": 9376 }
#   ],
#   "total_free_mb": 16152,
#   "tier": "beefy"
# }

# Also check what's running (and detect rogue llama-servers)
serve list
```

## When to trigger downscale

The 4-hourly scaling-check cron watches for these triggers:

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Free VRAM < 14 GB | Mild pressure | Consider Step 2 (offload aux MoE to CPU) |
| Free VRAM < 8 GB | Moderate pressure | Walk to Step 3-4 (drop context, then drop local aux) |
| Free VRAM < 4 GB | Critical pressure | Walk to Step 5+ (swap main to lighter model) |
| Free VRAM < 2 GB or OOM | Extreme | Walk to Step 6-7 (MoE main or API-only) |
| Local server unresponsive | Health failure | Skip to API fallback (`serve auto main --api`) |

**Never kill a model mid-response.** Always check for active sessions before stopping a server. The ladder only adapts *between* requests.

## Beefy tier — 7-step scaling ladder

This is the primary ladder for the Sirvir fleet. It uses model **archetypes** — the catalog is scanned by `serve recommend` to pick the best model matching each archetype slot.

```
STEP  STATE            ACTION                              MAIN ARCHETYPE         AUX ARCHETYPE        CTX
───── ──────────────── ─────────────────────────────────── ────────────────────── ──────────────────── ────────
  1   Ideal            Nothing                             27-28B dense (Q4)      35B MoE (3B active)  1M
  2   Mild pressure    Offload aux experts to CPU          27-28B dense (Q4)      35B MoE (cpu-moe)    1M
  3   Moderate         Drop context of both               27-28B dense (Q4)      35B MoE (3B active)  512K
  4   High             Drop aux, set aux to API            27-28B dense (Q4)      API vision (free)    262K
  5   Critical         Swap main to small dense            27B hybrid/Mamba (Q4)  API vision (cheap)   262K
  6   Extreme          Swap main to MoE (3B active)       35B MoE (3B active)    API vision (cheap)   132K
  7   API-only         No local serving viable             API main (Nous)        API vision (Nous)    1M
```

### Archetype reference

| Archetype | Typical Size (Q4) | VRAM | Examples (fleet catalog) |
|-----------|------------------|------|--------------------------|
| 27-28B dense | 14-17 GB | ~22 GB with KV cache | Darwin 28B Reason, Qwopus 27B |
| 27B hybrid/Mamba | 14 GB | ~16 GB | Prism Eagle 27B |
| 35B MoE (3B active) | 11-17 GB | ~11-17 GB | Carnice 35A3B, Darwin Apex |

### Walking the ladder down

```bash
# 1. Probe first
serve vram
serve list

# 2. Walk the ladder conservatively (one step at a time, re-probing between)
serve downscale

# serve downscale probes VRAM, recommends the appropriate step,
# and applies it — but only one step at a time. Re-run to go further.
```

### Step-by-step behavior

**Step 1: Ideal — Dual local at 1M**
Both models loaded, both at 1M context, full spec decoding. ≥8 GB free VRAM after loading both.
- main: 27-28B dense (e.g. Darwin 28B Reason, Q4_K_M, ~22 GB)
- aux: 35B MoE 3B-active (e.g. Carnice 35A3B, ~17 GB)
- Requires: dual GPU or 48GB+ VRAM

**Step 2: Mild pressure — Offload aux MoE experts to CPU**
Something else loaded onto a GPU. Move aux MoE expert weights to CPU RAM with `--cpu-moe`. Router + shared layers stay on GPU. Aux keeps serving, ~10 tok/s instead of ~30.
- main: unchanged
- aux: same MoE with `--cpu-moe-4` preset (drops to ~11 GB on GPU)

**Step 3: Moderate pressure — Drop context to 512K**
KV cache is the biggest variable. Shrink context on both:
- main ctx: 1M → 512K
- aux ctx: 1M → 512K
- Both still serving with spec decoding

**Step 4: High pressure — Drop local aux, API vision aux**
Kill the local aux. Aux routes to free API vision model:
- main: local dense @ 262K
- aux: Qwen 3.6 Plus (OpenRouter free, 1M ctx, vision) — 🟡 via OR
- Or: MiniMax M3 (NIM free, 1M ctx, vision) — ⚪ via NIM

**Step 5: Critical — Swap main to lighter dense/hybrid**
Main's VRAM footprint too large. Swap to a smaller model:
- main: 27B hybrid/Mamba (~14 GB, e.g. Prism Eagle) @ 262K
- aux: API vision (Qwen 3.5 Flash via Nous, $0.065/$0.26) — 🟢 NOUS+TG

**Step 6: Extreme — Swap to MoE main**
Swap to MoE (3B active per token, lower VRAM):
- main: 35B MoE 3B-active (e.g. Darwin Apex) @ 132K
- aux: API vision (Qwen 3.5 Flash via Nous) — 🟢 NOUS+TG
- Note: 132K is below the 262K floor — this is survival mode, not productive mode

**Step 7: API-only fallback — No local serving viable**
GPU fully occupied or down. Full cloud:
- main: GLM 5.2 (Nous) or DeepSeek V4 Pro (NIM free)
- aux: Qwen 3.5 Flash (Nous) or MiniMax M3 (NIM free)
- See API pairing matrix for all options

**Main is protected until Step 5.** Steps 1-4 only touch aux. The ladder never kills a model mid-response.

### Manual step application (when `serve downscale` isn't enough)

```bash
# Step 2: offload aux MoE experts to CPU
# Edit ~/.config/turbofit/models.yaml to add 'cpu-moe-4' to the aux model's presets, then:
serve stop <aux-alias>
serve <aux-alias>

# Step 3: drop context on both
# Edit models.yaml: set ctx: 524288 on both main and aux, then restart both
serve stop <main-alias> && serve <main-alias>
serve stop <aux-alias> && serve <aux-alias>

# Step 4: drop local aux, wire API aux
serve stop <aux-alias>
serve aux <api-vision-model>   # or: serve api use <rank> aux

# Step 7: full API fallback
serve stop-all
serve auto main --api
```

## Recovering when VRAM frees up

The ladder is bidirectional. When VRAM frees up (a process exited, a GPU was freed), walk back up.

```bash
# Probe to confirm VRAM is actually free
serve vram

# If free VRAM > 14 GB and we're at Step 2-4, scale back up one step
# Re-launch the local aux (Step 4 → Step 3)
serve aux carnice   # or whatever the local aux archetype is

# If free VRAM > 20 GB and we're at Step 5+, restore the main archetype
serve stop <lighter-main>
serve main darwin-28b-reason   # back to 27-28B dense

# If we're at Step 7 (API-only) and local GPU is back:
serve stop-all
serve auto main    # re-detects hardware, picks local
```

Recovery is conservative: one step at a time, re-probe between steps. Don't jump from Step 7 back to Step 1 without confirming VRAM is actually available.

## Cross-tier escalation

When hardware changes, the ladder transitions smoothly:

| Transition | Trigger | Action |
|-----------|---------|--------|
| Beefy → Modest | GPU failure / VRAM loss | Skip to Beefy Step 7 (API fallback) |
| Modest → Thin | GPU removed / VRAM < 8GB | Drop to Thin Step 1 (NIM free) |
| Thin → Modest | New GPU installed (8-24GB) | Jump to Modest Step 1 |
| Modest → Beefy | Second GPU / VRAM ≥ 24GB | Jump to Beefy Step 1 (local dual) |
| Any → API fallback | Network outage on local | Use `serve auto main --api` |

## 4-hourly scaling-check cron

```bash
# 1. Run serve vram — get live VRAM state
serve vram

# 2. If free VRAM < 14GB → consider downscale
# 3. Run serve downscale — walk the Beefy-tier ladder conservatively
serve downscale

# 4. Check that no sessions are active before killing a model
#    (convention: never kill a model mid-response)

# 5. Quick speed test on current backend (spot-check)
#    A simple timed generation against the running server:
curl -s -w "\n%{time_total}\n" http://127.0.0.1:11500/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"darwin-28b-reason","prompt":"Say hello.","max_tokens":32,"stream":false}'

# 6. Log state change to memory + consolidated log
# 7. Notify Discord if a model swap occurred
```

## Integration with turbofit core

- **turbofit** owns the catalog, `serve vram`, `serve downscale`, `serve auto`, and `serve stop`/`serve stop-all`. This skill documents the workflow and decision logic that sits on top of those commands.
- The scaling ladder reference lives at `turbofit/references/scaling-ladder.md` — this skill is the actionable workflow version of it.
- Catalog edits (changing `presets:`, `ctx:` on a model to apply a step) are made in `~/.config/turbofit/models.yaml`, then the model is restarted with `serve stop <alias> && serve <alias>`.
- The 4-hourly scaling-check cron is registered in Sirvir's profile config; this skill is the workflow that cron triggers.

## Cross-references

- **sirvir-bench** — owns the tok/s measurements that determine whether a model is above the 30 tok/s floor (Priority 2 in the optimization ladder); a model dropping below 30 tok/s is a downscale trigger
- **sirvir-serve** — external app servers consume VRAM too; sirvir-scale must account for external servers when probing pressure (a rogue external server on port 11530 is still holding VRAM)
- **sirvir-research** — owns the archetype table that the ladder's "main archetype" and "aux archetype" slots refer to
- **sirvir-budget** — API fallback (Step 4+) has a cost; sirvir-budget tracks whether the fallback is free (NIM) or paid (Nous/OR)
- **turbofit** (core skill) — `SKILL.md` documents the tier ladder, `serve vram`, `serve downscale`, and `serve auto`; `references/scaling-ladder.md` has the full step-by-step reference
