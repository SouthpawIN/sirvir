---
name: sirvir-serve
description: "External app endpoint serving skill. Documents how to spin up OpenAI-compatible endpoints for ANY app (not just Hermes), manage port assignments, stop external servers, and recommend the right model for a given use case. Includes the 'serve me a model' workflow. Complements the turbofit core skill — turbofit serves Hermes, sirvir-serve serves the world."
version: 1.0.0
author: SouthpawIN
license: MIT
tags: [serving, openai-compatible, external-apps, endpoints, llama-server, ports, turbofit]
metadata:
  hermes:
    tags: [serving, openai-compatible, external-apps, endpoints, llama-server, ports]
    related_skills: [turbofit, sirvir-scale, sirvir-research]
  changelog: |
    1.0.0 (2026-06-26): Initial split from turbofit monolith. Wraps the external-app serving workflow, port management, model recommendation for external use cases, and the 'serve me a model' UX.
---

# Sirvir-Serve — External App Endpoint Serving

Sirvir is not just a Hermes backend — he is a **model serving platform**. Any application can request an OpenAI-compatible endpoint. This skill documents how to spin up detached llama-server instances for external apps, manage ports, stop them, and recommend the right model for the job.

## When to use

Load this skill when any of the following are needed:

- A user says "serve me a model" (or "I need a model for <app>")
- An external app (coding assistant, chat UI, automation tool) needs a local OpenAI-compatible endpoint
- A specific model needs to be launched for a non-Hermes use case
- An external server needs to be stopped (free the port / free the VRAM)
- A port assignment needs to be checked or changed
- The user asks "what model should I run for <use case>?" and the answer is a local server for an external app

Trigger phrases: "serve me a model", "I need a model for", "launch a model for <app>", "openai-compatible endpoint", "local api for", "stop the external server", "what port is it on", "recommend a model for coding/chat/vision".

## Key differences from Hermes serving

| Aspect | Hermes serving | External serving |
|--------|---------------|------------------|
| Config wiring | Auto-wires into Hermes `config.yaml` | No Hermes config changes |
| Ports | Fleet main/aux ports (11500, 8082) | Separate port per external server |
| Model selection | Fleet main/aux only | Any model in the catalog |
| Lifecycle | Managed by fleet health checks | Persists until explicitly stopped or host reboots |
| Launch command | `serve main <alias>` / `serve aux <alias>` / `serve auto main` | `serve <alias>` (detached, no wiring) |

## The "serve me a model" workflow

This is the primary UX. When a user says "serve me a model" (or "I need a model for <app>"), follow this workflow:

### Step 1: Gather context

Ask the user (or infer from the request):

- **What are you doing?** coding, reasoning, vision, long context, general chat, all of the above
- **What app is it for?** (determines if a specific model type is needed — e.g. a coding assistant wants a coder model)
- **What's your budget?** zero-cost local only, small API budget, generous API budget
- **What's already running?** (check `serve list` — don't grab a port that's in use, and check VRAM with `serve vram`)

```bash
# Probe before acting (Sirvir's first convention)
serve vram
serve list
```

### Step 2: Consider local options

Scan the catalog for models that fit the VRAM and use case:

```bash
# Scan catalog, rank by fit (ctx≥64K, tok/s≥25, Q4, vision bonus, tier priority)
serve recommend

# Browse the full catalog (featured first, tier-ordered)
serve catalog
```

Apply the optimization priority (see sirvir-scale): 262K ctx → 30 tok/s → 1M ctx → max speed. A model that can't clear 262K + 30 tok/s on the available VRAM is not a viable local option — suggest API instead.

### Step 3: Consider API options

If local VRAM is tight or the user wants a specific API model:

```bash
# Show curated NVIDIA NIM models with pricing/vision/ctx
serve api list

# API model rankings live in references/api-model-rankings.md and api-pairing-matrix.md
```

Prefer free endpoints first (NIM: DeepSeek V4 Pro/Flash, MiniMax M3, Nemotron Ultra 550B), then cheapest Nous pairings.

### Step 4: Check creator quality (for local models)

When two local models are similar in benchmarks, the better-creator model wins. See sirvir-research for the creator quality database.

### Step 5: Present the recommendation

```
Recommended: <model_name> on <backend>
  Speed: ~XX tok/s
  Context: XXXK
  VRAM: XX GB (you have YY GB free)
  Cost: $X/month (or $0 if local)
  Why: <explanation>
  Creator: <creator_name> (quality score: X/10)
  Backend: <backend_name> — fastest available for this model

To launch: serve <alias>
```

Offer alternatives: "If you want more speed: <alt_model>. If you want more context: <alt_model>. If you want zero cost: <alt_model>."

### Step 6: Launch the endpoint

```bash
# Source the turbofit shim
source ~/.hermes/skills/turbofit/scripts/turbofit.sharco

# Launch a specific model (detached, returns endpoint URL + port + log path)
serve <alias>

# The command prints something like:
#   ✅ darwin-28b-reason launched on port 11500
#   Endpoint: http://127.0.0.1:11500/v1
#   Logs: ~/.local/share/turbofit/logs/darwin-28b-reason.log
#   PID: 12345
```

### Step 7: Return the endpoint to the user

The user points their app at `http://127.0.0.1:<port>/v1`. Any OpenAI-compatible app works:
- Coding assistants (Continue, Aider, Cursor, etc.)
- Chat UIs (Open WebUI, LibreChat, etc.)
- Automation tools (n8n, Langflow, etc.)
- Custom scripts using the OpenAI SDK

## Port management

### Default port assignments

| Use | Port | Notes |
|-----|------|-------|
| Hermes main | 11500 | Fleet-managed, don't reuse for external |
| Hermes aux | 8082 | Fleet-managed, don't reuse for external |
| External servers | 11530+ | Auto-assigned by `serve <alias>` if not specified in catalog |

### Checking what's running

```bash
# List all running servers + detect rogue llama-servers
serve list

# Check a specific port
curl -s http://127.0.0.1:11530/v1/models | head

# Check VRAM (to see what external servers are consuming)
serve vram

# Check for rogue llama-servers not managed by turbofit
ps aux | grep llama-server | grep -v grep
```

### Assigning a specific port

If an app needs a fixed port (e.g. it's configured to hit `http://127.0.0.1:11550/v1`), set it in the catalog:

```bash
# Register with a specific port
serve register my-external-model /path/to/model.gguf --port 11550

# Or edit ~/.config/turbofit/models.yaml directly to set port: 11550
# Then launch
serve my-external-model
```

### Port conflicts

If a port is already in use, `serve <alias>` will fail the health check and report it. Resolve by either:
- Stopping the conflicting server (`serve stop <alias>` or `serve stop-all`)
- Assigning a different port in the catalog

## Stopping external servers

```bash
# Stop a specific running server
serve stop <alias>

# Stop everything (Hermes + external — use with care)
serve stop-all

# Check what's still running after stopping
serve list
```

External servers persist until explicitly stopped or the host reboots. Always clean up when an external app is done — the VRAM is needed for the fleet.

## Model recommendation by use case

Quick reference for common external-app use cases. Always confirm with `serve recommend` and `serve vram` — these are starting points, not absolute.

| Use case | Archetype | Example model | Why |
|----------|-----------|---------------|-----|
| Coding assistant (Continue, Aider) | 27-28B dense coder | Qwopus 27B Coder-MTP | SWE-bench + HumanEval strong, spec decoding for speed |
| Long-context chat (Open WebUI) | 27-28B dense | Darwin 28B Reason | 1M ctx, strong reasoning |
| Vision tasks (image Q&A) | vision-capable model | Any model with `vision: true` + mmproj | Check mmproj matches (see turbofit SKILL.md pitfalls) |
| Fast chat (low latency) | 35B MoE 3B-active | Carnice 35A3B | 3B active per token = fast, still smart |
| Cheap API (no local GPU) | API free | DeepSeek V4 Pro (NIM) | Free, 1M ctx, strong reasoning |
| Premium API | API paid | GLM 5.2 (Nous) | Top-tier, Tool Gateway active |

### Vision model checklist

When recommending a vision-capable model, verify the mmproj file:

```bash
# Check that mmproj exists and isn't a stale symlink
ls -la <model_dir>/mmproj*.gguf
readlink -f <model_dir>/mmproj-F32.gguf   # if it's a symlink, verify the target

# mmproj MUST match the text model's n_embd:
#   Qwen3.6-27B dense (n_embd=5120)  → per-model mmproj-F32.gguf
#   Qwen3.6-35B-A3B MoE (n_embd=2048) → unsloth/Qwen3.6-35B-A3B-GGUF mmproj-BF16.gguf
# A mismatch crashes at load time with "mismatch between text model (n_embd = X) and mmproj (n_embd = Y)"
```

## Integration with turbofit core

- **turbofit** owns the catalog, `serve <alias>`, `serve stop`, `serve stop-all`, `serve list`, `serve register`, `serve recommend`, and `serve api list`/`serve api use`. This skill documents the external-app workflow that sits on top of those commands.
- The `serve <alias>` command is the same one used for Hermes serving — the difference is context (no `serve main`/`serve aux` wiring, just the detached launch).
- Catalog entries live in `~/.config/turbofit/models.yaml`; external models are registered there the same way as fleet models.
- VRAM consumed by external servers is visible to `serve vram` and affects sirvir-scale's pressure detection — an external server can trigger a fleet downscale.

## Cross-references

- **sirvir-scale** — owns the VRAM pressure detection that external servers contribute to; an external server holding VRAM can trigger a fleet downscale, and sirvir-scale's `serve vram`/`serve list` probes are the first step before launching any external server
- **sirvir-research** — owns the creator quality database used to break ties when recommending models; also owns the archetype table that recommendation use cases reference
- **sirvir-bench** — owns the benchmark scores (SWE-bench, HumanEval, MMLU) that justify "coder model" or "reasoning model" recommendations
- **sirvir-budget** — if the user's use case is better served by an API model, sirvir-budget tracks whether that fits the monthly budget
- **turbofit** (core skill) — `SKILL.md` documents `serve <alias>`, `serve stop`, `serve register`, `serve recommend`, `serve api list`, and the catalog schema; this skill is the external-app workflow that sits on top of them
