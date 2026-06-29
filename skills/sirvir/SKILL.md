---
name: sirvir
description: "Model fleet manager and intelligence engine for Hermes Agent. Autonomous model lifecycle manager — local serving, benchmarking, auto-scaling, API fallback, HuggingFace scanning, creator tracking, backend optimization, budget monitoring, and external app endpoint serving. Optimization priority: 262K context → 30 tok/s → 1M context → max speed."
version: 1.0.0
author: SouthpawIN
license: MIT
tags: [model-serving, benchmarking, vram, scaling, huggingface, llm, fleet-manager, turbofit, hermes-agent]
metadata:
  hermes:
    tags: [model-serving, benchmarking, vram, scaling, huggingface, llm, fleet-manager, turbofit, hermes-agent]
    related_skills: [turbofit, sirvir-bench, sirvir-research, sirvir-scale, sirvir-serve, sirvir-budget]
---

# Sirvir — Model Fleet Manager & Intelligence Engine

Sirvir is an autonomous Hermes Agent profile that manages your entire model layer. He operates the turbofit skill as his primary toolset and adds intelligence, automation, and competitive analysis on top.

## When to Use

- "Set up my local LLM" / "launch a model" / "what model should I run?"
- "My GPU is busy, scale down" / "check VRAM"
- "Serve me a model for [app]" — get an OpenAI-compatible endpoint
- "Benchmark my models" — run MMLU, GPQA, SWE-bench, HumanEval, AIME
- "Scan HuggingFace" — find new GGUF models, track creator quality
- "How much have I spent?" — token budget tracking
- "Fix mmproj" — verify and correct vision projector files
- "Swap main" / "swap aux" / "stop everything"

## Quick Start

```bash
# Install (requires turbofit first)
hermes skills tap add SouthpawIN/turbofit && hermes skills install turbofit
hermes skills tap add SouthpawIN/sirvir && hermes skills install SouthpawIN/sirvir/skills/sirvir

# Start the profile
hermes -p sirvir

# Then ask anything:
# > serve auto main
# > what model should I run?
# > serve me a model for my coding assistant
# > check mmproj
# > how much have I spent this month?
```

### Environment Variables

| Variable | Where | What It Enables |
|----------|-------|----------------|
| `NVIDIA_API_KEY` | Free at build.nvidia.com | Free API fallback (DeepSeek V4 Pro/Flash, MiniMax M3) |
| Nous Portal | nousresearch.com | **Primary** — Tool Gateway (Firecrawl, FAL, OpenAI TTS, Browser Use) + 10% OR credit bonus |
| `OPENROUTER_API_KEY` | openrouter.ai | Paid API models. Secondary to Nous |
| `HF_TOKEN` | huggingface.co/settings/tokens | HF model scanning + downloading |

## Sub-Skills

Sirvir ships with 6 focused sub-skills alongside the turbofit core:

- **turbofit** — Core serving engine (serve, catalog, daemon, scaling)
- **sirvir-bench** — Benchmarking workflow and score interpretation
- **sirvir-research** — HuggingFace scanning, creator tracking, pricing
- **sirvir-scale** — VRAM scaling ladder, optimization priority
- **sirvir-serve** — External app endpoint serving
- **sirvir-budget** — Token usage monitoring and budget alerts

## Inherited Skills

Sirvir also owns the model-routing skill and provider watchdog:

### model-routing

- **Skill**: `mlops/model-routing` — installed at `skills/mlops/model-routing/SKILL.md`
- **Scripts**: `model_router.py`, `router_integration.py` — installed at `skills/sirvir/scripts/`
- **What it does**: Dynamic model selection based on task type, priority, and cost. Task-type routing (financial, creative, coding, operations, quick, reasoning) with tier-aligned candidate lists.
- **When to load**: Before dispatching coding subagents, when reviewing routing policy, when the user asks "what model for this task?"

### provider_watchdog

- **Script**: `provider_watchdog.py` — installed at `skills/sirvir/scripts/`
- **What it does**: Conservative provider-outage detector. Pings your primary provider every 30 min, switches all profiles to a fallback on 3 consecutive failures, restores on recovery.
- **When to run**: `HERMES_HOME=~/.hermes python3 ~/.hermes/profiles/sirvir/skills/sirvir/scripts/provider_watchdog.py --check-only`

### apply_tier_routing

- **Script**: `apply_tier_routing.py` — installed at `skills/sirvir/scripts/`
- **What it does**: Applies premium/default/cheap tier routing to all profile config.yaml files in one pass. Supports --dry-run and --verify modes.
- **When to run**: After changing your tier assignments or provider strategy.

## Optimization Priority

Strictly enforced: **262K context → 30 tok/s → 1M context → max speed**

## Cron Jobs

- Daily 6am: HuggingFace scan + pricing + GitHub sync → Discord
- Daily 6:30am: Token budget tracking → Discord
- Every 4h: VRAM scaling check → Discord (alerts only)
- Hourly: Endpoint health (silent, alerts if down)
- Sunday 2am: Auto-benchmark main + aux + API competitive intel

## Profile Image

Generated following the Nous Research Style Guide — strict monochrome, retro manga 70s shoujo, industrial typewriter aesthetic.

## See Also

- [turbofit](https://github.com/SouthpawIN/turbofit) — core serving skill
- [sovth-config](https://github.com/SouthpawIN/sovth-config) — fleet config collection
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) — agent framework
