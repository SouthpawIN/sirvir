---
name: model-routing
description: "Dynamic model routing for task-specific optimization. Selects optimal model based on task type, priority, and cost."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [llm, routing, optimization, cost, speed]
---

# Model Routing

Dynamic model routing for real business workloads. Use stable profile lanes first, task-level overrides second, and delegation/specialized overrides only when the work clearly justifies them.

## Overview

This skill's operating model is:

1. **Profile lane first** — every profile should have a stable default model pair.
2. **Task override second** — only override the lane when the task clearly breaks the profile's normal workload.
3. **Delegation override third** — for coding bursts, deep research, or other specialized execution, explicitly set the worker/delegation model instead of letting subagents inherit accidentally.

The goal is not "pick the perfect model for every single prompt." The goal is a routing system that is simple, predictable, and aligned with business stakes.

Older Ollama/GLM/MiniMax benchmark sections below are retained as historical evidence and failure-mode documentation. They are not the primary live routing policy.

## Current operating model (2026-06-29)

### Tier plan (beta: ollama-cloud substitutes for Nous until 7/4 cutover)

Authoritative policy: `~/.hermes/profiles/sirvir/skills/sirvir/references/fleet-routing-policy.md`

Three-tier lane routing with hybrid provider strategy:

#### Premium lane

Use for business-critical reasoning, research, strategic planning, and orchestration.

Profiles:
- `default`
- `maf`
- `research`

Model pair (beta):
- main: `ollama-cloud` / `glm-5.2`
- compression: `ollama-cloud` / `glm-5.2`
- vision: `nvidia` / `minimaxai/minimax-m3` (NIM free)
- web_extract: `nvidia` / `minimaxai/minimax-m3` (NIM free)

After 7/4 cutover:
- main: `nous` / `glm-5.2`
- compression: `nous` / `glm-5.2`

#### Default lane

Use for implementation, operations, infra management, and production work.

Profiles:
- `rollout-auto`
- `sirvir`
- `garry-builds`

Model pair:
- main: `ollama-cloud` / `deepseek-v4-pro`
- compression: `ollama-cloud` / `deepseek-v4-pro`
- vision: `nvidia` / `minimaxai/minimax-m3` (NIM free)
- web_extract: `nvidia` / `minimaxai/minimax-m3` (NIM free)

#### Cheap lane

Use for comms, formatting, low-stakes drafting, and routine admin.

Profiles:
- `comms`
- `forge-frame`
- `personal`

Model pair:
- main: `ollama-cloud` / `deepseek-v4-flash`
- compression: `ollama-cloud` / `deepseek-v4-flash`
- vision: `nvidia` / `minimaxai/minimax-m3` (NIM free)
- web_extract: `nvidia` / `minimaxai/minimax-m3` (NIM free)

#### Fallback (all tiers)

- `openai-codex` / `gpt-5.4` — expires 7/4, will be re-evaluated at cutover

#### Why this lane split

- Premium profiles get the strongest text model (glm-5.2) for reasoning and compression
- Default profiles get deepseek-v4-pro — solid quality at same cost tier as premium on ollama-cloud
- Cheap profiles get deepseek-v4-flash — cheapest acceptable lane for low-stakes work
- Vision and web_extract standardized fleet-wide on nvidia/minimax-m3 (NIM free, good multimodal)
- Compression split off from vision/web_extract — different requirements (text quality vs multimodal)
- `default` acts as premium command center for synthesis and routing

#### Coding delegation override

For coding bursts dispatched via `delegate_task`, set `delegation.model` explicitly:
- `kimi-k2.7-code` — preferred coding model (6/25 benchmark: 10.1s avg, 100% success, clean output)
- `qwen3-coder:480b` — alternative (3.45s in June benchmark, but variable latency on ollama cloud)
- `glm-5.2` — fallback if neither coder model is available

Always clear `delegation.model` after the coding session to avoid wrong-model inheritance.

## Workload enhancement rules

### 1. Use lanes as the baseline operating system

Do not start from task-type routing every time. Start from the profile's lane and only override when needed.

### 2. Use task routing for exceptions, not for every prompt

Examples:
- a light-lane profile doing a strategic memo may deserve a premium override
- a premium profile doing repetitive low-stakes cleanup may stay on its default lane unless cost pressure is real

### 3. Keep one aux model everywhere unless there is a strong reason not to

Current standard aux:
- `qwen/qwen3.5-flash-02-23`

Why:
- 1M context
- vision-capable
- cheap relative to premium mains
- operationally simpler than maintaining different aux rules per profile

### 4. Treat delegation as a separate execution layer

The parent chat model and the delegated worker model do not have to be the same.

Use explicit delegation overrides for:
- coding bursts
- PR review / implementation sessions
- bulk research extraction
- other specialized execution where inheritance would pick the wrong model

### 5. Optimize for stability over theoretical perfection

A stable routing system with a few deliberate overrides is more valuable than constantly reshuffling models based on minor benchmark deltas.

## Workload classes

Use these business-aligned classes before falling back to narrow benchmark categories:

| Workload class | Typical work | Default routing |
|----------------|--------------|-----------------|
| **Executive / strategic** | Decisions, synthesis, planning, tradeoffs | Premium lane |
| **Client / business deliverable** | Proposals, research briefs, financial analysis, important brand copy | Premium lane |
| **Operational execution** | Follow-ups, triage, formatting, coordination, admin | Light lane |
| **Specialized coding / execution** | Repo work, debugging, PR review, builds, engineering bursts | Delegation override / specialized model |

## Special use case models

These are not the baseline profile models. They are explicit overrides for special workloads.

| Use case | Recommended model | Role | Notes |
|----------|-------------------|------|-------|
| **Coding delegation / production code** | `kimi-k2.7-code` | specialized worker | Preferred when dispatching coding-heavy subagents or implementation bursts |
| **Vision-heavy analysis** | `qwen/qwen3.5-flash-02-23` | aux / multimodal helper | Default shared aux because it is cheap, vision-capable, and operationally simple |
| **Long-context / document-heavy analysis** | premium lane first; escalate to long-context specialist only when needed | conditional override | Do not escalate automatically; only when the profile lane is clearly insufficient |
| **Math / proof-style reasoning** | use only as an explicit override after validation | experimental specialist | Historical candidates exist below, but treat them as opt-in, not default routing |
| **Chain-of-thought specialists** | use only as an explicit override after validation | experimental specialist | Slower and more expensive; avoid for normal reasoning |

Rule:
- If a special-use model is not clearly better for the current job, stay on the profile lane.

### Pitfall: reviewing a routing skill is not the same as editing it

If the user asks to "look at" or "reflect on" the routing skill, treat the skill as decision-support context first. Do not edit the skill just because it was consulted.

Correct sequence:
1. Read the routing skill and summarize what still applies vs what is outdated.
2. Propose the workload or routing improvement in plain language.
3. Wait for explicit user approval before editing `SKILL.md`, sync scripts, or profile copies.

Why this matters:
- consulting a skill and modifying a skill are different actions
- unsolicited edits create churn and can make the user feel like analysis turned into mutation without consent
- the best first deliverable is usually a cleaned-up recommendation, not an immediate patch

### Pitfall: profile renames require routing-skill maintenance

When a business profile is renamed, update the model-routing skill immediately if it carries any hardcoded profile lists or examples.

Minimum follow-up after a rename:
1. Update every `PROFILES = [...]` list in this skill's sync scripts.
2. Update the live routing map in `SKILL.md` to use the new slug.
3. Re-sync the skill to sub-profile copies so future sessions do not keep teaching the old name.
4. If the renamed profile has a managed gateway, restart it and verify the new profile slug is the one being supervised.

Example learned here:
- `construction` was renamed to `forge-frame`
- the sync scripts still referenced `construction`
- the gateway supervision slot also needed re-registration under the new slug before restart

### Watchdog alignment rule

The Provider Health Watchdog is a separate operational layer from the routing policy in this skill.

Current rule:
- if the watchdog still manages an older provider failover path (for example `ollama-cloud -> openai-codex`), keep its primary-model map aligned to the LIVE deployed stack
- do not update the watchdog to a future routing plan until that plan is actually wired into profile config and credentials
- when the routing plan changes materially, update all three together in the same turn:
  1. this skill's live routing map
  2. `~/.hermes/profiles/sirvir/skills/sirvir/scripts/provider_watchdog.py`
  3. `~/.hermes/profiles/sirvir/skills/sirvir/scripts/provider_watchdog.py`

This avoids a bad state where the skill teaches one routing policy, the watchdog restores another, and cron silently undoes intended model changes.

### Pitfall: review requests are not permission to edit the skill

When the user asks to review, reflect on, or critique the routing skill, treat that as an analysis request first.

Correct sequence:
1. Read the current skill and summarize what it implies for the live workload.
2. Call out what is outdated, conflicting, or operationally expensive.
3. Propose the cleaner routing policy.
4. Only patch the skill after the user explicitly asks to save or update it.

Why this matters:
- unsolicited edits create churn and can make the user feel like analysis turned into mutation without consent
- the best first deliverable is usually a cleaned-up recommendation, not an immediate patch

## When to Use

- **When defining or reviewing profile-level routing**
- **Before dispatching specialized delegated work**
- **When deciding whether a task should stay on its profile lane or use an override**
- **When cost, quality, or operational simplicity need to be traded off deliberately**

## Quick Start

```bash
# Route for a specific task type
python ~/.hermes/profiles/sirvir/skills/sirvir/scripts/model_router.py --task financial --priority speed

# Auto-detect task from prompt
python ~/.hermes/profiles/sirvir/skills/sirvir/scripts/model_router.py --prompt "Write brand voice for..." --priority quality

# List all routing tables
python ~/.hermes/profiles/sirvir/skills/sirvir/scripts/model_router.py --list

# Get Hermes slash command for switching
python ~/.hermes/profiles/sirvir/skills/sirvir/scripts/router_integration.py --task coding --priority quality --hermes-cmd
```

## Business Domains → Task Types

Map business use cases to optimal models. Not just task-type based — consider domain context.

| Business Domain | Use Cases | Task Type | Priority |
|-----------------|-----------|-----------|----------|
| **Marketing** | Campaign strategy, social planning, SEO | creative | balanced |
| **Marketing** | Image/video prompts (multimodal) | vision | quality |
| **Sales** | Outreach, follow-ups, CRM enrichment | creative | speed |
| **Sales** | Pipeline analytics | reasoning | balanced |
| **Operations** | Scheduling, logistics, fleet coordination | operations | speed |
| **Operations** | Capacity planning, forecasting | financial | balanced |
| **Creative** | Social media, video scripts, design prompts | creative | quality |
| **Creative** | Brand voice, tone guides | creative | quality |
| **Financial** | Modeling, IRR, valuation | financial | quality |
| **Financial** | Audit, compliance review | financial | quality |
| **Financial** | Quick calculations, ratios | quick | speed |
| **Technical** | Architecture, debugging, features | coding | balanced |
| **Technical** | Client deliverables (production) | coding | quality + high-stakes |

## Task Types

| Type | Description | Keywords |
|------|-------------|----------|
| **financial** | Revenue, EBITDA, IRR, valuation | "revenue", "profit", "cash flow", "investment" |
| **creative** | Brand, copy, marketing, social | "brand voice", "email", "headline", "copy" |
| **coding** | Implementation, debugging, API | "function", "algorithm", "debug", "refactor" |
| **operations** | Scheduling, logistics, routing | "schedule", "dispatch", "optimize", "capacity" |
| **quick** | Simple questions, conversions | "what is", "calculate", "convert", "capital of" |
| **reasoning** | Analysis, comparison, strategy | "analyze", "compare", "should i", "strategy" |

## Priorities

| Priority | Optimization | Best For |
|----------|--------------|----------|
| **speed** | Latency first | Client calls, real-time work |
| **balanced** | Equal weights | General use |
| **cost** | Subscription preference | High volume, drafts |
| **quality** | Output quality | Final deliverables |

## Tier Strategy

Models fall into three cost-quality tiers. Always benchmark before assigning a model to a tier — don't assume based on name or reputation.

| Tier | Models | Best For | Token Cost | Notes |
|------|--------|----------|------------|-------|
| **Cheap** | `deepseek-v4-flash` | Simple queries, personal tasks, quick lookups | Lowest | Hallucinates on real thinking tasks. Don't use for financial, coding, or anything requiring accuracy. |
| **Great+cheap** | `minimax-m2.5` | Conversation, orchestration, operations, quick tasks | Low | ⚠️ 34.8s on financial prompts, 50% success on coding. Good for ops/quick only. Always benchmark before expanding scope. |
| **Quality** | `deepseek-v4-pro`, `kimi-k2:1t`, `qwen3-coder:480b` | Highest | MAF/research/garry-builds defaults. Token-expensive but reliable. |
| **Quality (CONFIRMED 6/23)** | `glm-5.2` | Highest | Wins 3/4 categories in 3-way benchmark vs DS4Pro + M3 — **6.8× faster on coding**, 2.5× faster on financial, sub-second on quick. **Now the default profile model as of 6/24.** |
| **Quality (WORKER 6/24)** | `deepseek-v4-pro` | High | Replaced M3 on all 7 Diwan worker profiles. Beats M3 on latency in all 4 categories (1.3-2.9x). Same ollama-cloud cost tier. See `references/benchmark-3way-2026-06-23.md`. |

### Tier Assignment Rules (Hard Rules — Not Suggestions)

1. **BENCHMARK BEFORE ASSIGNING** — never add a model to routing tables without running it through `benchmark_fast.py` first. A model that sounds "great and cheap" (e.g. minimax-m2.5) may be 34s on financial or 50% on coding. Do not assume from hearsay or marketing. Run the test.
2. **Test across ALL task types** — a model that excels at quick ops may fail at financial or coding. Run the full benchmark suite across financial, creative, coding, and quick categories, not just one.
3. **Update routing tables immediately** — after benchmarking, update the SKILL.md routing tables and sync to all sub-profiles. Stale tables cause bad routing decisions.
4. **Document failure modes explicitly** — if a model fails a category (high latency, low success, or partial success), note it in the routing table so future sessions don't repeat the mistake.
5. **Prefer the model name from the provider's API** — "MiMo v2.5 Pro" might not match `minimax-m2.5` on Ollama. Verify the exact model ID from `/v1/models` before benchmarking.

### Pitfall: Assigning Without Testing

**Scenario:** Someone recommends a model as "great and cheap" for a specific use case. You add it to routing tables without testing.

**What goes wrong:** The model may have 34s latency on financial prompts, 50% success on coding, or other hidden failure modes that only surface under your actual workloads.

**Fix:** Always run `benchmark_fast.py` first and inspect the results before adding any model to routing tables. If the user asks "why is this model in the table?", the answer should be "because we benchmarked it", not "because it sounded good".

### Pitfall: Not checking the routing skill before dispatching coding subagents

**Symptom (verified 2026-06-25):** Controller dispatched `delegate_task` subagents for a production dashboard build without checking the model-routing skill. Subagents inherited `glm-5.2` (the orchestrator model) instead of `qwen3-coder:480b` (the benchmarked coding champion at 3.45s). User caught it.

**Why it happens:** `delegate_task` can't override the model per-call. If `delegation.model` is empty in config.yaml, children inherit the parent. The controller didn't load the routing skill before starting the build, so it didn't know to set `delegation.model` first.

**Prevention — before dispatching ANY subagent for coding/financial/creative work:**
1. **Load the model-routing skill** (`skill_view(name='model-routing')`) and check the routing table for the task type
2. **Set `delegation.model` and `delegation.provider` in config.yaml** to the routed model for that task type
3. **Verify the config took effect** with `hermes config get delegation.model`
4. **Then dispatch** — all subagents in that session will use the correct model
5. **After the build session, reset `delegation.model` to empty** if the next batch of work is a different task type

**Rule:** the routing skill is a pre-flight check for delegation, not just for `/model` slash commands. If you're about to `delegate_task` and you haven't checked the routing table, you're guessing.

## Auxiliary Model Architecture

Hermes supports separating the main chat model from auxiliary models used for side tasks (summarization, web page extraction, browser screenshots, session title generation, context compression).

This is a **recommended pattern** for token efficiency — use a quality model for thinking/conversation and a cheap model for grunt work.

### Recommendation (updated 2026-06-29)

Tier plan (beta: ollama-cloud substitutes for Nous until 7/4 cutover):

- **Premium main (default, maf, research):** `ollama-cloud` / `glm-5.2` — conversation, orchestration, routing, reasoning, compression
- **Default main (rollout-auto, sirvir, garry-builds):** `ollama-cloud` / `deepseek-v4-pro` — domain work, implementation, operations
- **Cheap main (comms, forge-frame, personal):** `ollama-cloud` / `deepseek-v4-flash` — comms, formatting, low-stakes admin
- **Compression (all profiles):** same as tier main model — split off from vision/web_extract
- **Vision + web_extract (all profiles):** `nvidia` / `minimaxai/minimax-m3` (NIM free, good multimodal)
- **Utility aux (skills_hub, approval, mcp, title_generation):** `nvidia` / `minimaxai/minimax-m3`
- **Workflow aux (triage_specifier, kanban_decomposer, profile_describer, curator):** `auto` (inherit main model)
- **Kanban decomposer + triage specifier:** inherit main model via `auto`
- **Fallback (all tiers):** `openai-codex` / `gpt-5.4` (expires 7/4)

**Why:** GLM-5.2 wins 3/4 benchmark categories (financial, coding, quick) including sub-second latency on quick tasks. DS v4 Pro is the solid middle lane. DS v4 Flash is the cheapest acceptable lane. M3 retained for vision/web_extract because it's free via NIM and verbose output is acceptable for side tasks. Compression moved off M3 to the tier text model because compression needs reliable instruction-following, not multimodal capability.

After 7/4 cutover:
- Premium main + compression: `nous` / `glm-5.2`
- Default and cheap lanes may stay on ollama-cloud or move to NIM depending on cost analysis
- Vision + web_extract: stay on `nvidia` / `minimax-m3`

### Configuration

By default, all auxiliary tasks use the main chat model (`auxiliary.*.provider: "auto"`). To override:

```yaml
auxiliary:
  ag:
    provider: ollama-cloud
    model: deepseek-v4-flash
  web:
    provider: ollama-cloud
    model: deepseek-v4-flash
  vision:
    provider: ollama-cloud
    model: qwen3-vl:235b
  compress:
    provider: ollama-cloud
    model: minimax-m3  # DS4F may not have 1M context — use M3
```

For per-profile configuration, add the `auxiliary` section to each profile's `config.yaml`.

### When to Apply

- **All profiles** — every profile benefits from aux model separation
- **Especially quality-tier profiles** (maf, research, garry-builds) — these default to expensive models and burn tokens fastest on side tasks
- **Skip** if the profile's main model is already cheap (personal with deepseek-v4-flash doesn't gain anything)

### Reference

See Hermes docs: https://hermes-agent.nousresearch.com/docs/user-guide/configuration#auxiliary-models

## Historical benchmark archive

This section is preserved for benchmark evidence, prior routing decisions, and debugging context. It is not the live routing policy. For live operation, use `## Current operating model (2026-06-26)` above.

Based on older June benchmark runs and older provider assumptions.

### Historical model assignments (as of 2026-06-25)

| Role | Model | Provider | Profiles | Notes |
|------|-------|----------|----------|-------|
| Default/orchestrator | `glm-5.2` | ollama-cloud | default | Wins 3/4 benchmark categories. Fallback: openai-codex/gpt-5.4 |
| Diwan workers (×7) | `deepseek-v4-pro` | ollama-cloud | comms, construction, garry-builds, maf, personal, research, rollout-auto | Replaced M3 on 6/24. Beats M3 on all 4 categories. Fallback: openai-codex/gpt-5.4 |
| **Coding (delegation)** | `kimi-k2.7-code` | ollama-cloud | — | **6/25 benchmark winner.** 10.1s avg, 100% success, 1446 avg tokens. Set via `delegation.model` when all subagents are coding. Clear after session. |
| Kanban decomposer | `glm-5.2` | ollama-cloud | — | Pinned via config |
| Triage specifier | `glm-5.2` | ollama-cloud | — | Pinned via config |
| Auxiliary vision | `minimax-m3` | ollama-cloud | all | Verbose output acceptable for vision tasks |
| Auxiliary web_extract | `minimax-m3` | ollama-cloud | all | Verbose output acceptable for extraction |
| Delegate_task subagents | (inherits parent or `delegation.model`) | — | — | Set `delegation.model` for task-specific routing; clear after use |

**Coding benchmark (6/25, 3 prompts × 3 models):**

| Model | Avg latency | Avg tokens | Success |
|-------|-------------|------------|---------|
| `kimi-k2.7-code` | 10.1s | 1,446 | 100% |
| `glm-5.2` | 9.9s | 1,819 | 100% |
| `qwen3-coder:480b` | 58.5s | 1,103 | 100% |

`kimi-k2.7-code` is the recommended coding model: clean output, good on async SQLAlchemy, more token-efficient than glm-5.2. `qwen3-coder:480b` was fastest in June (3.45s) but slow on 6/25 (85.5s on one prompt) — ollama cloud latency varies.

**Historical change history:**
- 6/25: Coding benchmark re-run with kimi-k2.7-code, qwen3-coder:480b, glm-5.2. kimi-k2.7-code recommended for delegation coding tasks.
- 6/24: All 7 Diwan profiles flipped from `minimax-m3` to `deepseek-v4-pro` based on 3-way benchmark showing DS beats M3 on all 4 categories at same cost tier.
- 6/23: 3-way benchmark confirmed GLM-5.2 as top performer (3/4 categories). Default profile already on GLM-5.2.
- 6/16: All profiles on M3 + DS4F aux strategy (now superseded).

### Speed Priority

| Task | Model | Provider | Latency | Notes |
|------|-------|----------|---------|-------|
| Financial | `glm-5.2` | ollama-cloud | 3.49s | 2.5x faster than DS4Pro, 3.4x faster than M3 |
| Creative | `deepseek-v4-pro` | ollama-cloud | 4.57s | 1.3x faster than M3, most concise (628 tok) |
| Coding | `kimi-k2.7-code` | ollama-cloud | 10.1s avg | 6/25 benchmark: 4.5s basic, 7.7s API, 18.1s system. Was glm-5.2 in 3-way (qwen not tested). |
| Operations | `deepseek-v4-pro` | ollama-cloud | — | Workers now on DS4Pro; ops is reasoning-adjacent |
| Quick | `glm-5.2` | ollama-cloud | 0.78s | Sub-second, lightest tokens (96) |
| Reasoning | `deepseek-v4-pro` | ollama-cloud | — | Workers on DS4Pro; DS4Pro wins reasoning in monthly matrix |

### Cost Priority (Ollama — Flat Subscription, as of 2026-06-25)

All models below are on ollama-cloud (tier 1, flat subscription). Cost is identical across models.

| Task | Model | Provider | Latency | Notes |
|------|-------|----------|---------|-------|
| Financial | `glm-5.2` | ollama-cloud | 3.49s | Fastest + fewest tokens (1035) |
| Creative | `deepseek-v4-pro` | ollama-cloud | 4.57s | Fastest + fewest tokens (628) |
| Coding | `kimi-k2.7-code` | ollama-cloud | Best coding model (6/25 benchmark, 10.1s avg, 1446 tok avg). GLM-5.2 close (9.9s, 1819 tok). qwen3-coder:480b was 58.5s avg — not viable. |
| Operations | `deepseek-v4-pro` | ollama-cloud | — | Workers on DS4Pro |
| Quick | `glm-5.2` | ollama-cloud | 0.78s | Sub-second, 96 tokens |
| Reasoning | `deepseek-v4-pro` | ollama-cloud | — | Retained from monthly matrix |

### Balanced (as of 2026-06-25)

| Task | Model | Provider | Notes |
|------|-------|----------|-------|
| Financial | `glm-5.2` | ollama-cloud | Fastest + cleanest output. Default profile already uses GLM-5.2 |
| Creative | `deepseek-v4-pro` | ollama-cloud | Most concise (628 tok). Workers on DS4Pro |
| Coding | `qwen3-coder:480b` | ollama-cloud | 3.45s, 780 tok, 100% success in June benchmark — actually the fastest coding model, not GLM-5.2. GLM-5.2 (6.75s) only "won" the 3-way because qwen3-coder was excluded from that run. |
| Operations | `deepseek-v4-pro` | ollama-cloud | Workers on DS4Pro |
| Quick | `glm-5.2` | ollama-cloud | Sub-second, lightest tokens |
| Reasoning | `deepseek-v4-pro` | ollama-cloud | Workers on DS4Pro |

**Model strategy (6/25):**
- **Default/orchestrator:** `glm-5.2` — fastest on 3/4 categories, already set
- **7 Diwan workers:** `deepseek-v4-pro` — beats M3 on all 4 categories, same cost tier
- **Coding delegation:** `kimi-k2.7-code` — 6/25 coding benchmark winner (10.1s avg, 100% success, clean output). Set `delegation.model` when dispatching coding subagents; clear after session.
- **Auxiliary (vision, web_extract):** `minimax-m3` — verbose but acceptable for side tasks
- **Kanban decomposer + triage specifier:** `glm-5.2`
- **Fallback:** all profiles → `openai-codex` / `gpt-5.4` if ollama-cloud goes down
- **delegate_task subagents:** set `delegation.model` for task-specific routing; clear after use to avoid wrong-model delegation. **Pre-flight rule:** check routing table before dispatching coding subagents — set `delegation.model: qwen3-coder:480b` + `delegation.provider: ollama-cloud` for coding work. kimi-k2.7-code is Garry's preferred coding model to test. Available coding models on ollama: `qwen3-coder:480b`, `kimi-k2.7-code`, `qwen3-coder-next`, `qwen3.5:397b`.

## Appendix A — Historical routing patterns and tooling

The rest of this skill is reference material. Use it when re-benchmarking, debugging older routing decisions, or reviving legacy tooling.

Appendix map:
- **Appendix A** — older routing patterns, switching flows, and cost reasoning
- **Appendix B** — benchmark maintenance cadence
- **Appendix C** — historical pitfalls and troubleshooting
- **Appendix D** — specialized override reference
- **Appendix E** — files and reference artifacts
- **Appendix F** — evaluation methodology

Do not treat these appendices as the default live routing policy unless the current operating model section above explicitly points you here.

### A1. High-Stakes Mode

For client deliverables, production code, or high-impact work:

```bash
python ~/.hermes/profiles/sirvir/skills/sirvir/scripts/model_router.py --task financial --high-stakes --priority quality
# → selects OpenAI for reliability
```

High-stakes mode:
- Prefers OpenAI (established quality record)
- Boosts quality weight in scoring
- Avoids experimental models

### A2. Integration with Hermes

### Manual Switching

```bash
# In Hermes session
/model gpt-5.5          # Switch to financial model
/model kimi-k2:1t       # Switch to creative model
/model qwen3-coder:480b # Switch to coding model
```

### Programmatic (from Skill)

```python
import sys
sys.path.insert(0, "~/.hermes/profiles/sirvir/skills/sirvir")
from model_router import select_model

# For financial task with speed priority
model, details = select_model("financial", priority="speed")
# Returns: ("gpt-5.5", {"provider": "openai-codex", "avg_latency_s": 9.37, ...})

# For creative task with cost priority (currently blocked — Ollama quota)
model, details = select_model("creative", priority="cost")
# Returns: ("gpt-5.4", {"provider": "openai-codex", ...}) — falls back to OpenAI

# Auto-detect task from prompt
model, details = select_model("auto", priority="balanced", prompt="Write brand voice...")
```

### Hermes Slash Command (from Skill)

```python
import sys, subprocess
sys.path.insert(0, "~/.hermes/profiles/sirvir/skills/sirvir")
from model_router import select_model

model, details = select_model("financial", priority="quality")
# Use /model slash command to switch
print(f"/model {details['provider']}:{model}")
# → /model openai-codex:gpt-5.5
```

### JSON Output for Scripts

```bash
python ~/.hermes/profiles/sirvir/skills/sirvir/scripts/model_router.py --task coding --priority speed --json
```

Output:
```json
{
  "model": "gpt-5.4-mini",
  "provider": "openai",
  "speed_score": 8.87,
  "cost_score": 7.0,
  "quality_score": 10.0,
  "weighted_score": 8.76,
  "avg_latency": "1.26s",
  "alternatives": [...]
}
```

### A3. Cost Analysis

### Subscription vs API (Fair Comparison)

**Critical:** Do NOT compare API tokens across providers without normalizing. DeepSeek is ~100x cheaper than OpenAI per token.

| Usage/Month | Ollama Pro | DeepSeek API | OpenAI API |
|-------------|------------|--------------|------------|
| 1M tokens | $20 | $1-2 | $5-15 |
| 5M tokens | $20 | $5-10 | $25-75 |
| 15M tokens | $20 | $15-30 | $75-200 |
| 50M tokens | $20 | $50-100 | $250-500 |

**Break-even:** ~5M tokens/month for Ollama Pro vs API

### Decision Framework

| Scenario | Best Choice | Rationale |
|----------|-------------|-----------|
| **High volume (15M+ tokens/mo)** | Ollama Pro | Flat $20/mo beats any API |
| **Burst usage (spikes + quiet)** | API | Only pay for what you use |
| **Client deliverables (time-sensitive)** | OpenAI Plus | Speed premium worth it |
| **Drafts / internal work** | Ollama Pro | Cost-efficient for iterations |
| **Math / Financial models** | Test DeepSeek API | May be cheaper than Ollama sub |

**Pitfall:** Comparing DeepSeek API cost to OpenAI Plus subscription is unfair. DeepSeek API is pay-per-token; OpenAI Plus is flat $20/mo. Fair comparisons:
  - DeepSeek API vs OpenAI API (both pay-per-token, DeepSeek is ~100x cheaper)
  - Ollama Pro ($20/mo) vs OpenAI Plus ($20/mo) (both flat subscription)
  - Ollama Pro vs your actual token usage across ALL API providers

### Your Usage Pattern

Agent operations (daily chat, coding, analysis): **10-30M tokens/month**
Recommendation: **Ollama Pro subscription** for cost-efficiency

### Pitfall: Incomplete Benchmark Set Produces Misleading Routing Winner

**Symptom (verified 2026-06-25):** The 6/23 3-way benchmark (DS v4 Pro vs M3 vs GLM-5.2) declared GLM-5.2 the coding winner. But it **excluded** `qwen3-coder:480b` and `kimi-k2.7-code` — the two models most relevant to coding. The routing table said "GLM-5.2 wins coding" because the models that would have beaten it weren't in the test.

**What went wrong:** Garry asked "did you use the model router to the coding model of choice?" The agent checked the routing table, saw GLM-5.2 listed as coding winner, and dispatched coding subagents on GLM-5.2. But the broader June benchmark had `qwen3-coder:480b` at 3.45s — faster than GLM-5.2's 6.75s. The 3-way was narrower than the prior benchmark, so its "winner" was misleading.

**Fix:** When a benchmark is used to update routing tables, always note **which models were excluded**. If a specialized model (e.g., a coding-specific model) exists in the inventory but wasn't in the benchmark, the routing table should say "won among tested models" not "is the best." When in doubt, re-run with the missing models included.

**Rule:** A routing table entry is only as trustworthy as the breadth of its benchmark. Before relying on a "winner," check whether the obvious candidates for that task type were actually tested.

### Pitfall: Model ID Drift — Deprecated Models Return 410 Gone

**Symptom (verified 2026-06-25):** `kimi-k2:1t` was listed in the June benchmark results. When re-running the benchmark on 6/25, `kimi-k2:1t` returned HTTP 410 Gone. The model had been deprecated and replaced by `kimi-k2.7-code`.

**Fix:** Before running any benchmark, verify model IDs against the live API:
```bash
python3 -c "
import urllib.request, json
env = open('~/.hermes/.env').read()
key = [l.split('=',1)[1].strip() for l in env.split('\n') if l.startswith('OLLAMA_API_KEY=***None
req = urllib.request.Request('https://ollama.com/v1/models', headers={'Authorization': f'Bearer {key}'})
data = json.loads(urllib.request.urlopen(req, timeout=30).read())
for m in sorted([x['id'] for x in data.get('data',[])]):
    print(m)
"
```

**Rule:** Model IDs on hosted providers change without notice. Always verify against `/v1/models` before benchmarking or updating routing tables. A stale model ID wastes a full benchmark run and produces a 0% success rate that looks like a model quality failure but is actually just a 410.

### Pitfall: Latency-fallback score (5.0) is too generous vs measured-but-slow models

**Symptom (verified 2026-06-22, glm-5.2 vs gpt-5.5 coding):** When using `priority=speed`, the router picked `gpt-5.5` (score 5.97) over `glm-5.2` (score 4.22) even though glm-5.2 was measured at 6.75s. gpt-5.5 had no benchmark data → `latency_score = 5.0` (fallback). glm-5.2's measured 6.75s → `latency_score = max(1.0, 10 - (6.75/3)*9) = max(1.0, -10.25) = 1.0` (clamped to floor).

**Why it stays silent:** A model with **no data** scores 5.0; a model **measured at 6.75s** scores 1.0. The router treats "I don't know how fast this is" as faster than "I measured it at 6.75s." For `speed` priority (60% latency weight), this is a major routing inversion.

**Why it matters:** gpt-5.5's quality baseline (9.5) further compounds the bias — high-quality + no-data beats measured-actually-fast.

**Two fixes (apply both):**

1. **Tighten the no-data latency fallback from 5.0 to 3.0** in `model_router.py` line ~158:
   ```python
   if avg_latency is not None:
       latency_score = max(1.0, min(10.0, 10.0 - (avg_latency / 3.0) * 9.0))
   else:
       latency_score = 5.0  # OLD
       latency_score = 3.0  # NEW — measured-but-slow beats unmeasured-high-quality
   ```

2. **Re-benchmark gpt-5.5 in the next monthly run** so it has actual data instead of relying on the fallback. The monthly cron (`979b95e18555`) covers this.

**Rule of thumb:** for `priority=speed`, prefer measured-data models over unmeasured-high-quality-baseline models. The fallback is a placeholder, not a recommendation.

### 3-way head-to-head benchmark pattern

When a new model is "candidates" tier, don't add it to routing tables on a single 1v1 benchmark against the current default — the new model may win on speed but lose on quality, or vice versa. **Run a 3-way benchmark: new model + current default + nearest competitor.** Same 4 prompts (financial, creative, coding, quick), all three models, all four categories.

**Why 3-way, not 1v1:**
- 1v1 winner may be relative (X beats Y but Z beats both)
- 3-way forces relative comparison and surfaces category-specific winners
- Sample outputs side-by-side reveal qualitative differences (verbosity, formatting) the numbers hide
- Quality baselines (`QUALITY_BASELINE` dict) shift with new data

**The 3-way benchmark script** is at `~/.hermes/profiles/sirvir/skills/sirvir/benchmark_glm52_minimal.py` — drop-in for any new model. Set `MODELS = [<new>, <current_default>, <nearest_competitor>]` and run.

**Output structure:** 4 categories × 3 models = 12 requests, all in one run. Side-by-side latency + tokens + sample output (first 400 chars). Total runtime ~2-3 minutes for fast models, 5-10 for slow ones.

**Pattern (verified 2026-06-22, glm-5.2 vs deepseek-v4-pro vs minimax-m3):**
- glm-5.2 won 3/4 categories (financial, coding, quick)
- deepseek-v4-pro won 1/4 (creative — most concise + fastest)
- minimax-m3 lost all 4 but was tested for completeness
- Routing table updated: glm-5.2 as primary for financial/coding/quick, DS v4 Pro for creative

**Don't:** add a new model to "Quality" tier without running the 3-way. The 6/22 `glm-5.2` candidate status was earned by this benchmark, not by marketing or hearsay.

## Appendix B — Benchmark maintenance

**Note:** Garry specified benchmarks should run **biweekly** (every 2 weeks), but the current cron `979b95e18555` is set to monthly (first Sunday). This should be updated to biweekly cadence. The cron schedule needs changing from `0 6 1-7 * 0` (first Sunday monthly) to a biweekly pattern like `0 6 * * 0` with `repeat: 0` (every Sunday) or a true biweekly expression. Verify with Garry before changing.

Benchmark runs automatically first Sunday of each month at 6 AM.

### Pitfall: degraded monthly benchmark runs are provider-health signals, not clean routing verdicts

**Symptom (verified 2026-06-28):** The monthly `benchmark_fast.py` run completed, but one provider tier returned `HTTP 429 Too Many Requests` on every benchmarked request. Only the other provider's models produced successful rows. If you feed that result directly into the router, the routing table can collapse to "healthy provider wins every category" even though the outcome reflects temporary provider unavailability rather than true model quality.

**What to do:**
1. Still archive the run — it is real evidence.
2. Label the run explicitly as **degraded** or **provider-health-limited**.
3. Compare against the **last healthy benchmark snapshot**, not just the immediately previous file, before changing normal-mode recommendations.
4. Split recommendations into two layers:
   - **temporary degraded-mode routing** — what to use right now while the provider is failing
   - **normal-mode routing to restore after recovery** — preserve the last known good winners from the healthy benchmark
5. Call out any categories that lost coverage entirely because all candidates for that category were on the degraded provider.

**Rule:** a monthly benchmark can update routing in two different ways:
- **quality/latency update** when multiple providers/models completed normally
- **provider-health update** when one provider fails broadly

Do not treat a provider-health outage as proof that the surviving provider permanently displaced the prior winner.

Reference: `references/degraded-benchmark-provider-health.md`

**Results delivery:** Discord (gateway channel), not Telegram.

Results archive:
- `~/.hermes/profiles/sirvir/skills/sirvir/benchmark_fast_results_YYYY-MM.json`
- `~/.hermes/profiles/sirvir/skills/sirvir/references/model_routing_matrix.md` (updated)

To force update:
```bash
cd ~/.hermes/profiles/sirvir/skills/sirvir
python3 benchmark_fast.py
```

## Appendix C — Historical troubleshooting and pitfalls

### No benchmark data

```
Error: No benchmark results found
```

Fix: Run benchmark first
```bash
cd ~/.hermes/profiles/sirvir/skills/sirvir
python3 benchmark_fast.py
```

### Model not available

```
Error: Model 'gpt-5.5' not found
```

Fix: Check provider auth
```bash
# Ollama
grep OLLAMA_API_KEY ~/.hermes/.env

# OpenAI (OAuth)
hermes auth list
```

### Recommendations outdated

If recommendations seem wrong after running benchmark:

1. Check benchmark results age
2. Re-run benchmark
3. Verify no failures in benchmark output

### Fallback provider not triggering (Layer 1 dead)

**Symptom:** `fallback_providers` is set in config.yaml but Hermes never falls back when the primary provider returns 429.

**Root cause:** `hermes config set fallback_providers '["openai-codex"]'` serializes the value as a YAML **string** (`fallback_providers: '["openai-codex"]'`) instead of a proper YAML list. Hermes reads a string, not a list of providers, so the fallback chain is empty.

**Fix:** Edit the YAML directly to use list format:
```bash
sed -i "s/fallback_providers: '\\(\\.*\\)'/fallback_providers:\n- \1/" ~/.hermes/config.yaml
```
Or for sub-profiles, ensure the format is:
```yaml
fallback_providers:
- openai-codex
```
Not:
```yaml
fallback_providers: '["openai-codex"]'   # WRONG — string, not list
```

**Verify:**
```bash
grep -A2 "fallback_providers" ~/.hermes/config.yaml
# Should show:
# fallback_providers:
# - openai-codex
```

See `references/fallback-providers-yaml-format-bug.md` for full reproduction and fix.

### Cron job runs once then stops

**Symptom:** A cron job with `schedule: 30m` runs exactly once and never again. The job state shows `completed` instead of `scheduled`.

**Root cause:** Cron jobs default to `repeat: once` even when a recurring schedule is set. The `repeat` field must be explicitly set to `0` (forever) for recurring behavior.

**Fix when creating:**
```bash
hermes cron create 30m --name "My Job" --script my_script.sh --no-agent
# Then immediately update to make it recurring:
hermes cron update <job_id> --repeat 0
```

**Verify:**
```bash
hermes cron list | grep -A5 "My Job"
# Check: repeat=forever, state=scheduled (not completed)
```

### Cron job created but never runs

**Symptom:** A cron job was created, `hermes cron list` shows it, but it never fires. Hours later, the system still hasn't run it.

**Root cause:** The cron job was created with `repeat: once` (the default) instead of `repeat: forever`. After the first run, the job enters `state: completed` and never fires again. This is easy to miss because the `schedule` field shows the recurring interval but `repeat` controls whether it actually repeats.

**Fix:** After creating any recurring cron job, immediately verify with `hermes cron list`:
1. The job appears in the list
2. `state=scheduled` (not `completed`)
3. `repeat=forever`
4. `next_run_at` has a future timestamp
5. `enabled=true`

If `repeat=once`, update it: `hermes cron update <job_id> --repeat 0`

**Prevention:** Always set `repeat=0` explicitly when creating recurring cron jobs, or update immediately after creation.

## Appendix D — Special use case reference (historical / specialized overrides)

Use this section only when the baseline lane policy is clearly insufficient. These are explicit overrides for specialized tasks, not default profile routing. **Most are not benchmarked recently — use with caution.**

| Task Type | Primary | Fallback Chain | Notes |
|-----------|---------|----------------|-------|
| **Vision (images)** | `qwen3-vl:235b` | Ask user to describe → text model | NOT TESTED |
| **Math proofs** | `minimax-m2.7` | `deepseek-v4-pro` → `gpt-5.5` | Math-specialized (NOT TESTED) |
| **Long context (>50K)** | `kimi-k2:1t` | `gpt-5.5` | 128K context window |
| **Chain-of-thought** | `kimi-k2-thinking` | `kimi-k2:1t` | Reasoning-specialized (NOT TESTED) |
| **Ultra-cheap** | `deepseek-v4-flash` | API only | NOT TESTED - avoid gemma3:4b |
| **Production code** | `kimi-k2.7-code` | `glm-5.2` → `gpt-5.5` | Quality first. 6/25 benchmark confirmed kimi-k2.7-code writes cleanest production code. |

### Fallback Handling

```
Vision:
  qwen3-vl:235b (Ollama) 
    → If fails → Ask user to describe → Use text model

Math:
  minimax-m2.7 (Ollama, NOT TESTED)
    → deepseek-v4-pro (Ollama, TESTED)
    → gpt-5.5 (OpenAI, TESTED)

Long Context:
  kimi-k2:1t (Ollama, 128K)
    → gpt-5.5 (OpenAI, 200K)

Chain of Thought:
  kimi-k2-thinking (Ollama, NOT TESTED)
    → kimi-k2:1t (Ollama, TESTED)
```

### When to Use Special Overrides

- **Vision:** User uploads image/screenshot, asks for visual analysis
- **Math:** Symbolic math, proofs, multi-step calculations (not simple arithmetic — use `quick` for that)
- **Long Context:** Document >50 pages, large codebases, multi-file analysis
- **Chain-of-thought:** Complex reasoning requiring explicit intermediate steps

**Pitfall:** Do NOT use chain-of-thought or other special overrides for simple tasks — they are slower, more expensive, and add operational complexity. Stay on the profile lane unless the workload clearly demands otherwise.

## Appendix E — Files and reference artifacts

- `~/.hermes/profiles/sirvir/skills/sirvir/scripts/model_router.py` — Core routing logic
- `~/.hermes/profiles/sirvir/skills/sirvir/scripts/router_integration.py` — Hermes integration
- `~/.hermes/profiles/sirvir/skills/sirvir/references/model_routing_matrix.md` — Full routing matrix (auto-generated by `model_router.py --list`)
- `~/.hermes/profiles/sirvir/skills/sirvir/references/benchmark_fast_results.json` — Current benchmark data
- `~/.hermes/profiles/sirvir/skills/sirvir/benchmark_fast_report.md` — Human-readable report
- `~/.hermes/profiles/sirvir/skills/sirvir/benchmark_fast.py` — Benchmark runner script
- `~/.hermes/profiles/sirvir/skills/sirvir/benchmark_coding_3way.py` — Coding-only 3-way benchmark script (created 6/25)
- `~/.hermes/profiles/sirvir/skills/sirvir/scripts/provider_watchdog.py` — Proactive health watchdog (cron `d85df0885c22`, every 30 min)
- `scripts/sync-skills-to-profiles.py` — Sync SKILL.md to all 7 sub-profile copies after updates

### Reference Files

- `references/model-inventory-2026-06-07.md` — Tested vs available models, cost analysis, selection policy
- `references/ollama-pro-inventory-2026-06-07.md` — Full Ollama Pro model inventory with token economics
- `references/benchmark-results-2026-06-07.json` — Machine-readable benchmark data
- `references/model-router-architecture-2026-06-15.md` — Router build-out: dead skill → live scripts, config changes
- `references/provider-watchdog-failsafe.md` — Two-layer fail-safe: Hermes fallback chain + proactive health watchdog cron
- `references/benchmark-scoring-cross-category-bug.md` — Router scored models by (provider, model) instead of (provider, model, category), causing cross-category score overwrites
- `references/benchmark-3way-2026-06-23.md` — 3-way benchmark results: DS v4 Pro vs M3 vs GLM-5.2 (12/12 requests, all categories). Drove the 6/24 decision to flip Diwan workers from M3 to DS v4 Pro.
- `references/benchmark-coding-3way-2026-06-25.md` — Coding-specific 3-way benchmark: kimi-k2.7-code vs qwen3-coder:480b vs glm-5.2 (9/9 requests, 3 coding prompts). Drove the 6/25 decision to use kimi-k2.7-code for coding delegation.
- `references/benchmark-coding-3way-2026-06-25.md` — Coding-focused 3-way: kimi-k2.7-code vs qwen3-coder:480b vs glm-5.2 (9/9 requests, 3 coding prompts). Drove the 6/25 decision to set delegation.model to kimi-k2.7-code for coding subagents.
- `references/coding-benchmark-comparison-2026-06-25.md` — Why GLM-5.2 didn't actually win coding (qwen3-coder:480b was excluded from the 3-way). delegate_task routing lesson.
- `references/benchmark-coding-qwen-vs-glm-2026-06-25.md` — Coding model comparison showing qwen3-coder:480b (3.45s) actually beats GLM-5.2 (6.75s). Corrected the false "GLM-5.2 wins coding" from the incomplete 3-way benchmark.
- `references/fallback-providers-yaml-format-bug.md` — YAML string vs list bug that killed Layer 1 fallback
- `references/cron-job-repeat-once-pitfall.md` — Cron jobs default to one-shot; how to make them recurring

### E1. See Also

- `llm-benchmark` skill — How to run benchmarks, test prompts, token economics
- Cron job `979b95e18555` ("Monthly Model Benchmark") — runs `benchmark_fast.py` first Sunday of each month at 6 AM UTC, delivers to Discord

---

## Appendix F — Evaluation Methodology

**Core principle: Evaluate ALL use cases up front, not ad-hoc.** Before committing to a model strategy, map every business domain→task type and pre-select the optimal model for each. This prevents wasted tokens on mismatched work.

### Pre-Planning Checklist

1. **Inventory all use cases** — List every business domain (marketing, sales, operations, creative, financial, technical)
2. **Map task types** — Which models handle each domain? (creative → kimi-k2:1t, financial → gpt-5.5, coding → qwen3-coder:480b)
3. **Calculate token economics** — Subscription break-even vs API pay-per-token for expected volume
4. **Benchmark before deploying** — Run actual prompts from YOUR workflows, not generic tests
5. **Set routing rules** — Define fallback chains (primary → backup → last resort)

### Dimensions to Measure

| Dimension | What to Test | Why It Matters |
|-----------|--------------|----------------|
| **Latency** | Time to first token, total completion | Developer productivity, real-time work |
| **Accuracy** | Correctness on domain-specific tasks | Client deliverables, financial models |
| **Cost** | Tokens × price per token OR flat subscription | Budget constraints |
| **Subscription vs API** | Flat rate vs pay-per-use | High volume → subscription; burst → API |
| **Quality** | Polish, tone, formatting | Client-facing work |

### Common Evaluation Mistakes

1. **Unfair cost comparisons** — DeepSeek API is ~100x cheaper than OpenAI API per token. Compare subscriptions to subscriptions, APIs to APIs.

2. **Single-model thinking** — One model doesn't fit all. Match model to use case: `kimi-k2:1t` for creative, `gpt-5.5` for financial, `qwen3-coder:480b` for code.

3. **Not re-evaluating** — Model rankings change monthly. The cron job at `~/.hermes/profiles/sirvir/skills/sirvir/benchmark_fast.py` runs the first Sunday of each month.

4. **Ad-hoc routing** — Picking models task-by-task wastes tokens. Pre-plan all use cases.

### Use Case → Task Type Mapping

**Business context determines task type, not just prompt keywords.**

| Business Domain | Example Prompts | Task Type |
|-----------------|-----------------|-----------|
| Marketing campaign | "Write brand voice guide for..." | creative |
| Financial model | "Calculate EBITDA given..." | financial |
| Code review | "Review this PR for..." | coding |
| Dispatch routing | "Optimize schedule for..." | operations |
| Quick question | "What's the capital of..." | quick |
| Strategy analysis | "Compare approaches for..." | reasoning |"