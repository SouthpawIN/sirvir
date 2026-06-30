---
name: sirvir
description: "Model fleet manager and intelligence engine for Hermes Agent. Autonomous model lifecycle manager — local serving, benchmarking, auto-scaling, API fallback, HuggingFace scanning, creator tracking, backend optimization, budget monitoring, and external app endpoint serving. Optimization priority: 262K context → 30 tok/s → 1M context → max speed."
version: 1.0.0
author: example-user
license: MIT
tags: [model-serving, benchmarking, vram, scaling, huggingface, llm, fleet-manager, turbofit, hermes-agent]
metadata:
  hermes:
    tags: [model-serving, benchmarking, vram, scaling, huggingface, llm, fleet-manager, turbofit, hermes-agent]
    related_skills: [turbofit, sirvir-bench, sirvir-research, sirvir-scale, sirvir-serve, sirvir-budget, model-routing]
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
- "Does it make sense using the ollama max subscription instead of per-token?" — subscription vs per-token cost comparison (delegate to sirvir-budget)
- "Eval the cost spectrum" — fleet-wide cost modeling (delegate to sirvir-budget)
- "Fix mmproj" — verify and correct vision projector files
- "Swap main" / "swap aux" / "stop everything"
- "Test aux models" / "A/B test aux providers" / "debug aux routing" — verify aux models work for vision, web_extract, and other aux tasks; test alternative aux candidates; diagnose silent aux failures

## Recommendation workflow for "what model should I run?"

When the user asks for a model recommendation, prefer this order:

1. Probe live hardware and fleet state first (VRAM / running models / current routing) when those signals are available.
2. If live probing is unavailable in the current shell, fall back to the curated lineup and hardware-tier guidance.
3. In the answer, clearly separate:
   - live-verified facts (measured on-box now)
   - lineup-based recommendations (best fit from the curated fleet policy)
4. If the recommendation is not live-verified, say so explicitly instead of presenting it as a measured fit.
5. Give three lanes when useful: best overall, best premium API, and best free/zero-cost path.
6. Qualify provider recommendations by actual usage tier when possible: light, moderate, heavy, or corp-level. Use historical token/session evidence first, then profile/workload shape, then user-stated expectations.
7. Do not present NVIDIA NIM as a production-default aux or main answer for heavy Hermes usage. It is acceptable as a light-use or experimental recommendation, and in some moderate cases for light profiles only.

This prevents overclaiming when the current environment cannot see the user's GPUs or serving stack, while still giving a useful recommendation immediately.

## Pitfall: when the user asks to review the current setup, audit deployed reality and workload — not just the lineup

If the user asks for a more specific recommendation based on "what I have now", do not stop at the curated Sirvir/Turbofit policy.

Run a three-layer review and report them separately:
1. documented policy — what Sirvir/Turbofit says the ideal stack should be
2. deployed config — what each relevant profile's `config.yaml` currently points to for main + aux
3. observed workload — what the profile `state.db` session history shows is actually carrying the work

## Pitfall: when the user asks to review ALL profiles, classify the fleet into premium / default / cheap lanes from live profile evidence

If the user asks for routing assignments across profiles, do not answer from profile names alone and do not stop at the root config.

Audit every active profile under the profile root and build a fleet-wide underwriting table from two live signals:
1. deployed config — what each profile is currently pointed at for main + aux
2. observed workload — what that profile's own `state.db` shows for session count, total tokens, top models, top sources, and cache behavior

Then assign each profile to one of three routing lanes:
- premium — high-stakes or high-volume profiles where quality clearly justifies the expensive lane
- default — solid reasoning profiles that should live on the smart middle lane with premium escalation only
- cheap — low-stakes, low-volume, or coordination-heavy profiles that should prefer the low-cost lane

Minimum checklist for this class of request:
- enumerate `${HERMES_HOME}/profiles/*/config.yaml`
- enumerate `${HERMES_HOME}/profiles/*/state.db`
- **ALSO check `${HERMES_STATE_DB}`** — the root "default" profile (orchestrator) stores its state.db at the root, not under `${HERMES_HOME}/profiles/default/`. This profile is typically the largest by token volume. Missing it produces a materially wrong fleet analysis.
- for each profile, read the current main model from `config.yaml`
- for each profile with a `state.db`, aggregate `sessions`, total tokens, top `model` values, top `source` values, and cache-read behavior from the `sessions` table
- call out where current deployed config is still on a stop-gap provider/model and differs from the recommended lane
- recommend one fleet-wide aux default when the evidence supports standardization

Recommended response shape:
- Premium: <profiles>
- Default: <profiles>
- Cheap: <profiles>
- Why each profile landed there
- Current deployed mismatch vs recommended cutover

Minimum checklist for this class of request:
- read the target profile's `config.yaml` and the root `${HERMES_CONFIG}` when present
- compare other active profiles' `config.yaml` files to see whether the fleet is actually aligned or still API-first
- inspect `state.db` directly to measure where tokens and sessions really go; prefer the `sessions` table and aggregate `input_tokens`, `output_tokens`, `cache_read_tokens`, and top `model` values
- call out explicitly when a local stack (for example Darwin + Carnice) is documented policy but not currently deployed
- check for live turbofit state under the profile home (`home/.config/turbofit`, `home/.local/share/turbofit`) before claiming a local stack is active
- if no active local catalog / pid / port / launch-string evidence exists, say the local stack is an intended cutover target rather than current reality
- when the heavy workload sits on other profiles, optimize for those lanes first; do not over-index on Sirvir's own profile if it is a small share of fleet usage

Recommended response shape:
- Current deployed setup
- Current workload concentration by profile
- Recommendation for "keep as-is" vs "intentional cutover"
- Exact launch commands only for the deliberate cutover target, clearly labeled as such

## Quick Start

```bash
# Install (requires turbofit first)
hermes skills tap add example-user/turbofit && hermes skills install turbofit
hermes skills tap add example-user/sirvir && hermes skills install example-user/sirvir/skills/sirvir

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

## Pitfall: provider fitness under heavy Hermes load matters more than nominal free pricing

Do not recommend NVIDIA NIM as a production-default provider just because it is free or cheap.

Support-backed operational finding (2026-06-30): under heavy Hermes usage, NVIDIA rate limiting and delay can make aux tasks miss their window, after which the main model effectively does the work anyway. That creates a false-economy routing pattern: cheap provider on paper, but degraded aux completion and worse effective routing under load.

Recommendation rule:
- light users: NVIDIA can still be suggested
- moderate users: NVIDIA only for light profiles or clearly low-stakes aux work
- heavy or corp-level users: do not recommend NVIDIA as the default aux/main provider; classify it as experimental or light-duty only

When recommending providers, use this evidence order:
1. state.db historical token/session usage
2. observed workload concentration by profile
3. dashboard/provider usage snapshots
4. explicit user-stated expected usage

See `references/provider-fitness-by-usage-tier.md` for the full classification guide.

## Pitfall: separate recommended policy from deployed reality

When reviewing a routing recommendation, routing skill, or model-plan session, do not assume the written plan is already live.

## Pitfall: when the user asks to define a major Sirvir PR, force a gated spec instead of a loose brainstorm

If the user is planning a substantial Sirvir change — especially one that rewrites skills, profile policy, routing logic, helper scripts, or budget guidance — do not jump straight into freeform analysis.

Use this sequence:
1. define the precise criteria for a great result first
2. anchor the output format to a prior successful artifact or report shape
3. run the interview in small decision gates and explicitly lock each gate before moving on
4. bias toward compartmentalized modules/spec blocks rather than one giant rewrite blob
5. require explicit user confirmation on scope boundaries, source-of-truth hierarchy, acceptance criteria, and migration behavior
6. before finalizing the spec, get a second-AI review focused on missing layers, contradictions, stale assumptions, and breakage risk
7. once the spec is approved, derive a file-by-file execution plan before implementation
8. after the implementation lands, do a hardening pass before PR prose: eliminate misleading data formats, wire any dead policy knobs, restore true fleet-vs-filtered semantics, and add executable validation coverage for the new cases
9. run the executable validation and live smoke checks yourself after the hardening pass
10. then get a second-AI audit against the original approved spec, focused on compliance gaps, preserved behavior, and regression risk
11. only draft the PR body after the implementation, hardening, validation, and second-AI audit passes are complete

This is especially important when the user says they want small or compartmentalized specs. Treat that as a workflow requirement, not a style preference.

See `references/usage-tier-provider-policy-execution-plan.md` for the post-spec execution-plan pattern and runtime-first edit order.

## Pitfall: usage-tier classification must layer on top of deployed/discovered model classification, not replace it

When implementing Sirvir routing or budget changes that introduce usage tiers (light / moderate / heavy / corp), do not delete the existing discovery layer that answers:
- what the profile is currently configured to run
- what model actually dominated observed usage
- which deployed lane that current or dominant model belongs to

Correct implementation shape:
1. keep deployed-config discovery (`config.yaml` main/aux provider+model)
2. keep observed-usage discovery (`state.db` top models / dominant 30d model)
3. classify those discovered models into the existing lane vocabulary (premium / default / cheap or equivalent)
4. add usage-tier classification as a second layer
5. let usage tier govern provider eligibility and recommendation policy (for example NVIDIA allowed only for light-use), not erase the discovery output
6. present both layers together in reports and router output:
   - deployed lane / dominant model lane
   - profile tier / fleet tier / governing tier

Why this matters:
- the user may be asking both "what is deployed now?" and "what should eligibility be under the new policy?"
- removing the discovery/model-classification layer destroys the comparison between current reality and the new governance layer
- the correct answer is usually a two-layer underwriting view: observed deployment + policy classification

If you catch yourself rewriting a router or audit script and the output loses current-lane / dominant-model visibility, stop and restore that layer before continuing.

## Pitfall: after a second-AI audit finds substantive implementation gaps, any follow-up fixes require a fresh re-audit

When a Sirvir policy / routing implementation gets an independent audit and then you change code in response to that audit, do not treat the earlier review as still valid.

Required sequence:
1. run the first independent audit against the implemented state
2. fix every substantive finding before declaring the work ready
3. rerun local verification after the fixes (`py_compile`, executable validators, and at least one live router/audit invocation)
4. dispatch a fresh second-AI re-audit against the new post-fix state
5. only draft the PR body after the re-audit result comes back clean enough

This matters because a review against revision N does not verify revision N+1. Post-audit fixes can introduce new regressions, so the independent pass must be refreshed.

## Pitfall: hardening Sirvir config parsing means checking live list-shaped config fields, not just nested mappings

When replacing or improving config parsing in `model_router.py`, `audit_fleet.py`, or related helper scripts, do not stop after proving `model` and `auxiliary` mappings still work.

Minimum parser verification:
- load the live root `${HERMES_CONFIG}`
- confirm `fallback_providers` parses as a list of provider/model dicts
- confirm `toolsets` parses as a list, not an empty mapping
- confirm nested aux slots still parse correctly (`vision`, `web_extract`, `skills_hub`, `approval`, `mcp`, `title_generation`, etc.)

Why this matters:
- a shallow or pseudo-YAML parser can appear to work for the fields Sirvir immediately reads while silently corrupting list-shaped config surfaces
- that kind of partial success creates a false sense of safety in routing / audit code

## Pitfall: deployed-lane classification must prefer the most specific model-name match

When classifying a deployed or dominant model into premium/default/cheap lanes, do not rely on first-hit substring matching over unordered lane buckets.

Required implementation rule:
- flatten the lane-name candidates and match the longest / most specific model strings first
- add executable checks for overlapping names such as:
  - `deepseek-v4-flash` -> `cheap`
  - `deepseek-v4-pro` -> `default`
  - `minimaxai/minimax-m3` -> `cheap`

Why this matters:
- `deepseek-v4` is a substring of `deepseek-v4-flash`
- naive matching can silently misclassify the deployed lane as `default` instead of `cheap`
- that breaks the preserved discovery layer the user explicitly wants kept intact during usage-tier work

If a usage-tier refactor touches routing or audit scripts, extend the validator so lane classification is locked by executable checks, not just by inspection.

## Pitfall: migration suggestions should surface all deployed NVIDIA aux slots under non-light governing tiers

When the usage-tier policy says NVIDIA is not eligible outside light usage, the router's migration suggestions must not only flag `vision`.

At minimum, inspect and surface all currently deployed NVIDIA-backed aux roles discovered in config, including where present:
- `vision`
- `web_extract`
- `skills_hub`
- `approval`
- `mcp`
- `title_generation`
- sibling utility aux roles such as `triage_specifier`, `kanban_decomposer`, `profile_describer`, or other discovered NVIDIA slots

The goal is a truthful migration prompt that compares deployed reality to recommendation policy, not a partial warning that understates exposure.

## Pitfall: when the user asks to recall "our plans," prioritize the preserved strategy, not the rebuild mechanics

If the user asks what the plan was for models, routing, budget, or cache economics, do not default to the latest profile-maintenance session just because it is the freshest hit.

Use this retrieval order:
1. preserved handoff/report artifacts that summarize conclusions
2. skill references that encode the durable planning method
3. live config only as a separate "currently deployed" layer

For the June 2026 Sirvir planning thread, start with `references/strategic-plan-recall.md` and the preserved handoff report it points to. Answer with the strategic budget/model conclusions first, then optionally note rebuild or cutover mechanics only if they are actually relevant.

Use this three-layer audit frame and report each layer separately:
1. documented policy — what the skill or routing document says should run
2. deployed config — what profile `config.yaml` files actually point to right now
3. helper automation — whether router/watchdog/helper scripts still encode the older stack

Why this matters:
- model-routing work often lands in stages across multiple sessions
- the user may intentionally keep a beta plan in documentation before wiring it into live configs
- watchdog and fallback automation may need to stay aligned to the currently deployed stack until cutover day

Minimum audit checklist for routing reviews:
- confirm whether the top-of-skill policy and deeper routing tables agree or whether old tables are historical only
- confirm whether master and sub-profile skill copies are synced after a patch
- confirm whether profile configs still point at the previous live provider/model pair
- confirm whether helper automation (`model_router.py`, `router_integration.py`, `provider_watchdog.py`) still targets the older routing world
- execute the router in JSON mode for at least one representative task and compare its chosen winner against the raw benchmark file; do not trust the router summary blindly
- inspect the router scoring math for clamps or weighting that can erase real latency differences and produce a false winner
- run the watchdog in `--check-only` mode and verify the state file agrees with the printed status before recommending changes
- if the new plan is not yet deployed, recommend a staged cutover instead of rewriting automation prematurely

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

## Inherited Skills (2026-06-29)

Sirvir now owns the model-routing skill and provider watchdog — previously external, now part of his wheelhouse.

### model-routing

- **Skill**: `mlops/model-routing` — installed at `${HERMES_PROFILE_DIR}/skills/mlops/model-routing/SKILL.md`
- **Scripts**: `model_router.py`, `router_integration.py` — installed at `${SIRVIR_SKILL_DIR}/scripts/`
- **Master copy**: `${HERMES_PROFILE_DIR}/sirvir/skills/mlops/model-routing/SKILL.md` (synced to all 7 profile copies)
- **What it does**: Dynamic model selection based on task type, priority, and cost. Task-type routing (financial, creative, coding, operations, quick, reasoning) with tier-aligned candidate lists.
- **When to load**: Before dispatching coding subagents, when reviewing routing policy, when the user asks "what model for this task?"

### provider_watchdog

- **Script**: `provider_watchdog.py` — installed at `${SIRVIR_SKILL_DIR}/scripts/`
- **Live copies**: `${HERMES_PROFILE_DIR}/sirvir/skills/sirvir/scripts/provider_watchdog.py` and `${HERMES_PROFILE_DIR}/sirvir/skills/sirvir/scripts/provider_watchdog.py` (sha256-synced)
- **What it does**: Conservative provider-outage detector. Pings ollama-cloud every 30 min, switches all profiles to openai-codex/gpt-5.4 on 3 consecutive failures, restores on recovery.
- **When to run**: `HERMES_HOME=${HERMES_HOME} python3 ${HERMES_PROFILE_DIR}/sirvir/skills/sirvir/scripts/provider_watchdog.py --check-only`

### Three-layer alignment rule

When the tier plan changes, update all three layers in the same turn:
1. **Profile configs** — all profile `config.yaml` files
2. **Helper scripts** — `model_router.py`, `provider_watchdog.py`, `router_integration.py`
3. **Model-routing skill** — master + sync to all profile copies

Failing to update all three together causes drift: the skill teaches one policy, the watchdog restores another, and cron silently undoes intended changes.

For session-specific maintenance history and cutover procedures, see `references/session-history-2026-06-29.md`.

## References

- `references/auxiliary-compression-routing.md` — how to interpret compression warnings when the main session is temporarily running on Codex or another stop-gap provider; distinguishes Codex timeout, explicit NVIDIA config failure, and safe no-drop aborts.
- `references/nous-debug-report-workflow.md` — how to produce both a narrative report and a real Hermes `/debug`-style share bundle for Nous Research, including the fallback of importing `hermes_cli.debug.build_debug_share` from the repo venv when the `hermes` launcher is unavailable. API: `build_debug_share(*, log_lines=200, expiry=7, redact=True) -> DebugShareResult` with `.urls` dict.
- `references/nous-bug-report-aux-reasoning-2026-06-30.md` — full bug report: reasoning models (Step 3.7 Flash, DeepSeek V4 Pro, Nemotron reasoning variants) return `content: null` via NIM, making them structurally incompatible with Hermes aux tasks. Includes reproduction steps, affected models, and recommended fixes.
- `references/profile-rebuild-handoff.md` — how to preserve Sirvir session state into the user's brain before deleting/rebuilding the profile, including the `0_Admin/daily/` handoff-note pattern and ad-hoc verification convention.
- `references/strategic-plan-recall.md` — how to reconstruct previously-written Sirvir model/routing/budget plans from preserved handoff artifacts and skill references instead of over-indexing on the latest rebuild-maintenance session.
- `references/fleet-tier-config-cutover.md` — how to apply the premium/default/cheap tier routing to all profile config.yaml files, including the beta provider substitution pattern, the watchdog alignment rule, and the overlap map with external model-routing/watchdog scripts.
- `references/routing-watchdog-audit.md` — checklist for reviewing routing skills, router scripts, and provider watchdogs by separating documented policy, deployed config, and helper automation; includes the requirement to execute the router and compare it against benchmark data instead of trusting the summary.
- `references/usage-tier-hardening-validation.md` — post-audit validation checklist for usage-tier hardening work: parser probes, filtered-fleet checks, migration-suggestion completeness, and the rule to refresh the second-AI audit after post-audit fixes.
- `references/usage-tier-provider-policy-pr-spec.md` — interview-derived spec pattern for large Sirvir policy PRs: define success criteria first, use gated decision blocks, classify usage at profile + fleet level, keep NVIDIA light-use only, and require a second-AI review before finalizing the spec.
- `references/session-history-2026-06-29.md` — session-specific maintenance history: issues fixed, 7/4 cutover procedure, and three-layer alignment rule.

## See Also

- [turbofit](https://github.com/example-user/turbofit) — core serving skill
- [sovth-config](https://github.com/example-user/sovth-config) — fleet config collection
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) — agent framework
