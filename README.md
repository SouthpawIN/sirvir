# Sirvir — Model Fleet Manager & Intelligence Engine

![Sirvir Profile](profile.png)

**Sirvir** is an autonomous Hermes Agent profile that manages your entire model layer — local serving, benchmarking, auto-scaling, API fallback, HuggingFace scanning, creator quality tracking, backend optimization, token budget monitoring, and external app endpoint serving.

![Sirvir System Diagram](banner.png)

> *TOWARDS SELF-IMPROVEMENT*

---

## Table of Contents

- [What Sirvir Does](#what-sirvir-does)
- [Install](#install)
- [Quick Start](#quick-start)
- [When to Use Sirvir](#when-to-use-sirvir)
- [Example Prompts](#example-prompts)
- [Commands](#commands)
- [Sub-Skills](#sub-skills)
- [Cron Jobs](#cron-jobs)
- [Interactions with Other Agents](#interactions-with-other-agents)
- [Optimization Priority](#optimization-priority)
- [Hardware Tiers](#hardware-tiers)
- [Profile Image](#profile-image)

---

## What Sirvir Does

Sirvir is the **infrastructure owner** for your model fleet. He doesn't just serve models — he actively manages their entire lifecycle:

| Responsibility | What It Means |
|---------------|---------------|
| **Local model serving** | Launches, wires, and monitors local llama-server instances via turbofit |
| **External app endpoints** | Spins up OpenAI-compatible endpoints for ANY app, not just Hermes |
| **HuggingFace scanning** | Continuously scans for new GGUF models matching your archetypes |
| **Creator quality tracking** | Maintains a database of model creators and their track records |
| **API model benchmarks** | Competitive intelligence on all monitored API models (local vs API) |
| **Auto-backend optimization** | Tests llama.cpp / vLLM / Ollama / SGlang per model, finds the fastest |
| **Token budget monitoring** | Tracks real spend from Hermes state.db against a monthly budget |
| **Model suggestions** | Recommends models based on hardware, use case, and budget |
| **Consolidated logging** | All activities stream to Discord, blog, and GitHub simultaneously |
| **VRAM scaling** | Auto-detects pressure, walks scaling ladder, never kills mid-response |

---

## Install

### Prerequisites

Sirvir requires the [turbofit](https://github.com/SouthpawIN/turbofit) skill to be installed first — it's the core serving engine.

```bash
# 1. Install turbofit (required dependency)
hermes skills tap add SouthpawIN/turbofit
hermes skills install turbofit

# 2. Add the Sirvir repo and install
hermes skills tap add SouthpawIN/sirvir
hermes skills install SouthpawIN/sirvir/skills/sirvir

# 3. Start using it
hermes -p sirvir
```

After install, `source ~/.bashrc` to get the `serve` and `name` shell commands.

### Optional Environment Variables

| Variable | Where to Get It | What It Enables |
|----------|----------------|----------------|
| `NVIDIA_API_KEY` | Free at [build.nvidia.com](https://build.nvidia.com) | Free API fallback (DeepSeek V4 Pro/Flash, MiniMax M3) |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) | Paid API models (GLM 5.2, Qwen 3.7 MAX) |
| `HF_TOKEN` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | HuggingFace model scanning + downloading |

Set these via `hermes setup` or in your `.env` file.

---

## Quick Start

```bash
# Start Sirvir
hermes -p sirvir

# Then ask it anything:
```

```
> What model should I run on my RTX 3090?
> Serve me a model for my coding assistant
> Check if my mmproj files are correct
> How much have I spent this month?
> Scan HuggingFace for new 27B models
```

---

## When to Use Sirvir

### Use Sirvir when you need to:

- **"Set up my local LLM"** — auto-detect GPU, pick best model, launch, wire Hermes
- **"Launch a model"** — serve any GGUF from your catalog
- **"What model should I run?"** — get a recommendation based on hardware + budget
- **"My GPU is busy, scale down"** — walk the VRAM scaling ladder
- **"I need vision"** — find and verify the correct mmproj for any model
- **"Serve me a model for [app]"** — get an OpenAI-compatible endpoint for any application
- **"How much have I spent?"** — track token usage against your monthly budget
- **"Benchmark my models"** — run MMLU, GPQA, SWE-bench, HumanEval, AIME
- **"Scan HuggingFace"** — find new models, track creator quality
- **"Swap main" / "Swap aux"** — change the fleet's serving configuration
- **"Stop everything"** — kill all running servers

### Don't use Sirvir for:

- General coding tasks (use Chizul or your default profile)
- Discord community questions (use Anser)
- Research deep-dives (use Crow)
- Profile editing (use Klerik)

---

## Example Prompts

### Model Setup
```
> Serve auto main
  → Detects GPU, picks best local model, launches, wires Hermes config

> Serve auto main --api --free
  → Forces free API mode (DeepSeek V4 Pro via NVIDIA NIM, no GPU needed)

> Serve auto aux --vision
  → Pick best vision-capable aux model

> Serve auto main --ui tui
  → Launch + start Hermes TUI
```

### Model Suggestions
```
> What should I run on a single RTX 4090 (24GB)?
  → Sirvir recommends: Darwin 28B Reason (main) + Carnice 35A3B (aux)
    "Your 24GB VRAM fits a 27B dense main (17GB) + 35B MoE aux (11GB).
     Vision on both. 38 tok/s main, 110 tok/s aux. Zero API cost."

> What's the cheapest setup with vision?
  → "DeepSeek V4 Flash (free NIM) + MiniMax M3 (free NIM, vision).
     Zero cost. 1M context. Works on any hardware — even no GPU."
```

### External App Serving
```
> Serve me a model for my coding assistant
  → Launches a model on an available port, returns:
    "Endpoint: http://127.0.0.1:11530/v1
     Model: qwopus-27b-coder-mtp (100 tok/s, vision, 17GB)
     Point your app at that URL with any OpenAI-compatible client."

> I need a fast model for batch processing
  → "Prism Eagle 27B — 121 tok/s, only 14GB VRAM.
     Endpoint ready at http://127.0.0.1:11531/v1"
```

### Benchmarking
```
> Benchmark darwin-28b-reason
  → Runs MMLU, GPQA, SWE-bench, HumanEval, AIME
    "GPQA: 89.39% | MMLU: 82.1% | HumanEval: 74.8% | AIME: 43.3%
     Tier S confirmed. Smartest dense model in the fleet."

> Compare all 27B models
  → "1. Prism Eagle (121 tok/s, GPQA 86.2%)
     2. Darwin Reason (38 tok/s, GPQA 89.4%)
     3. Qwopus v2 MTP (100 tok/s, GPQA 84.1%)"
```

### VRAM Management
```
> Check VRAM
  → {"gpu_count": 2, "free_GB": 47.5, "per_gpu_free_MiB": [24158, 24519]}

> Downscale
  → "VRAM nominal. No scaling needed. Both GPUs have >20GB free."

> Downscale (under pressure)
  → "Step 2: Offloading aux MoE experts to CPU (--cpu-moe).
     Expected ~10 tok/s aux throughput. Main unaffected."
```

### mmproj Management
```
> Check mmproj
  → "✅ darwin-28b-reason: n_embd=5120 mmproj=5120 (27B dense) (888MB)
     ✅ carnice: n_embd=2048 mmproj=2048 (MoE) (860MB)
     All 15 vision models verified."

> Fix mmproj for my-new-model
  → "Downloading mmproj-F32.gguf from HF repo...
     ✅ Downloaded to /models/my-new-model/mmproj-F32.gguf
     ✅ Catalog updated. Vision enabled."
```

### Budget Tracking
```
> How much have I spent this month?
  → "Month-to-date: $3.42 / $50.00 budget (6.8%)
     Yesterday: 2.1M input tokens, 840K output, 1.8M cache reads
     Cache savings: $8.91 (84% cache hit rate)
     You're underutilizing — consider upgrading to GLM 5.2 for better reasoning."
```

---

## Commands

Sirvir operates through the turbofit `serve` command plus its own sub-skills:

### Core Serving (turbofit)
```bash
serve auto main [--vision] [--api] [--free] [--ui tui|dashboard|gateway|desktop|herm]
serve auto aux  [--vision] [--api] [--free] [--ui ...]
serve <alias>                         # Launch a specific model
serve string <alias>                  # Dry run — print launch command
serve stop <alias>                    # Stop a specific model
serve stop-all                        # Stop everything
serve list                            # List running + detect rogue servers
```

### Catalog & Registration
```bash
serve catalog                         # Browse models (featured first, tier-ordered)
serve register <alias> <path>         # Register a new model
           [--launcher llama-cpp|ollama|vllm|sglang] [--port N]
serve recommend                       # Rank all models by fit
name <alias> <path>                   # Shortcut for register
```

### Hardware & VRAM
```bash
serve vram                            # Live GPU VRAM probe (JSON)
serve fit <model> [ctx]               # Check if model fits in VRAM
serve downscale                       # Walk scaling ladder
```

### mmproj Management
```bash
serve mmproj check                    # Verify all vision models have correct mmproj
serve mmproj fix <alias>               # Find/download/set correct mmproj
```

### Benchmarking
```bash
serve bench <alias>                   # Run lm-eval-harness (MMLU, GPQA, etc.)
serve bench compare_27b               # Head-to-head comparison
```

### API Fallback (NVIDIA NIM — free)
```bash
serve api list                        # Show curated free NIM models
serve api use <rank|api_id> [main|aux] # Wire a NIM model into config
```

### Hermes Config Wiring
```bash
serve main <alias> [--ui tui|dashboard|gateway|desktop|herm]
serve aux  <alias> [--ui ...]
serve herm <alias>                    # Launch + main + herm TUI
serve herm                            # Auto-pick main + launch herm TUI
```

### Systemd Daemons
```bash
serve daemon install <alias> [--idle N]
serve daemon remove <alias>
serve daemon start <alias>            # Proxy only — backend wakes on ping
serve daemon stop <alias>             # Stop + kill backend (frees VRAM)
serve daemon status [alias]
serve daemon list
```

### Research
```bash
python3 scripts/research-models.py    # Fetch live pricing, update database
bash scripts/sync-github.sh           # Sync to GitHub
```

---

## Sub-Skills

Sirvir ships with 5 focused sub-skills alongside the turbofit core:

| Skill | What It Does |
|-------|-------------|
| **turbofit** | Core serving engine — launch, catalog, scale, daemon management |
| **sirvir-bench** | Benchmarking workflow — MMLU, GPQA, SWE-bench, HumanEval, AIME. Score interpretation, tier feedback loop |
| **sirvir-research** | HuggingFace scanning, OpenRouter pricing, creator quality tracking, GitHub sync |
| **sirvir-scale** | VRAM scaling — 3-tier detection, 7-step Beefy ladder, optimization priority |
| **sirvir-serve** | External app endpoints — "serve me a model" workflow, port management |
| **sirvir-budget** | Token usage monitoring, monthly budget, alert thresholds, upgrade suggestions |

---

## Cron Jobs

Sirvir runs autonomously on a schedule:

| Schedule | Job | Delivers To |
|----------|-----|------------|
| **Daily 6:00 AM** | HuggingFace scan + OpenRouter pricing + model DB update + GitHub sync | Discord |
| **Daily 6:30 AM** | Token budget tracking + spend analysis + upgrade suggestions | Discord |
| **Every 4 hours** | VRAM probe + scaling check (downscale if pressure detected) | Discord (alerts only) |
| **Hourly** | Endpoint health check (silent — only alerts if endpoint is down) | Discord (alerts only) |
| **Sunday 2:00 AM** | Auto-benchmark main + aux models + API model competitive intel | Discord |

---

## Interactions with Other Agents

Sirvir is part of a multi-agent fleet. Here's how he interacts with each:

| Agent | Role | Interaction |
|-------|------|-------------|
| **Senter** | Triage orchestrator | Sirvir reports infrastructure changes; Senter routes model-related tasks to Sirvir |
| **Chizul** | Kanban worker | Chizul runs benchmark tasks on Sirvir's behalf; Sirvir provides VRAM alerts when Chizul's builds consume GPU |
| **Crow** | Research | Crow does deep research; Sirvir provides raw pricing/performance data for analysis |
| **Klerik** | Profile editor | When Sirvir changes a model endpoint, Klerik ensures all fleet configs are updated |
| **Anser** | Discord support | Anser handles user-facing questions; Sirvir provides technical details |
| **Nous Girl** | Brainstormer | Nous Girl generates ideas; Sirvir evaluates whether the fleet's models can handle them |

### Example fleet interaction:

```
User: "Set up a local coding model"
  → Senter routes to Sirvir
  → Sirvir: "serve auto main --vision"
  → Sirvir detects GPU, picks Qwopus 27B Coder MTP, launches on port 11500
  → Sirvir notifies Senter: "Main model changed to qwopus-27b-coder-mtp"
  → Senter: fleet continues with new model
```

---

## Optimization Priority

When optimizing any local model, Sirvir follows this priority **strictly**:

1. **262K context length** — minimum viable for productive use
2. **30 tok/s** — minimum viable speed for interactive use
3. **1M context length** — stretch goal
4. **As fast as possible** — maximize speed once all thresholds are met

Never trade context for speed unless 262K is achieved. Never trade 30 tok/s for more context unless 30 tok/s is achieved.

**The ladder: `262K → 30 tok/s → 1M → max speed`**

---

## Hardware Tiers

Sirvir auto-detects your hardware tier via `nvidia-smi`:

| Tier | VRAM | Setup | Default Main | Default Aux |
|------|------|-------|-------------|-------------|
| **Beefy** | ≥24GB | Local main + local aux | 27-28B dense (Q4) | 35B MoE (3B active) |
| **Modest** | 8-24GB | API main + free/cheap aux | DeepSeek V4 Pro (API) | MiniMax M3 (NIM free) |
| **Thin** | <8GB or no GPU | API main + API aux | DeepSeek V4 Flash (NIM free) | MiniMax M3 (NIM free) |

No NVIDIA GPU → defaults to Thin (API-only, zero cost).

---

## Profile Image

The Sirvir profile image was generated following the [Nous Research Style Guide](https://github.com/SouthpawIN/nous-style-guide) — strict monochrome (pure black #000000 + white #FFFFFF), retro manga 70s shoujo style, bold line art, screentone halftone shading, industrial typewriter aesthetic, Swiss grid layout.

The character is a focused engineer with over-ear headphones featuring a circuit-board headband, surrounded by GPU monitoring displays and VRAM gauge dials. The "262K" and "30 tok/s" labels reference the optimization priority ladder.

---

## See Also

- [turbofit](https://github.com/SouthpawIN/turbofit) — the core model serving skill Sirvir operates
- [sovth-config](https://github.com/SouthpawIN/sovth-config) — top-level fleet config collection
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) — the agent framework
- [Nous Style Guide](https://github.com/SouthpawIN/nous-style-guide) — brand identity for visual output
