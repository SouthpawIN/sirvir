# Fleet tier config cutover — 2026-06-29

## Purpose

This reference documents the exact procedure for applying the premium/default/cheap tier routing to all profile config.yaml files. It covers the beta provider substitution pattern, the watchdog alignment rule, and the overlap map with external model-routing/watchdog scripts.

## Beta provider substitution pattern

During the beta period (6/29 - 7/4), ollama-cloud substitutes for Nous as the provider for all text lanes:

- text lanes (main + compression): ollama-cloud (beta) -> nous (post-beta)
- vision/web_extract: nvidia/NIM (stays the same, free)
- utility aux slots (skills_hub, approval, mcp, title_generation): nvidia/NIM (stays the same)

On cutover day, only the provider field changes for premium text lanes — the model names stay the same.

## Tier layout

### Premium (research only)
- main: ollama-cloud / glm-5.2
- compression: ollama-cloud / glm-5.2
- vision: nvidia / minimaxai/minimax-m3
- web_extract: nvidia / minimaxai/minimax-m3
- fallback: openai-codex / gpt-5.4 (expires 7/4)

### Default (default, example-maf-profile, example-rollout-profile, sirvir, example-builds-profile)
- main: ollama-cloud / deepseek-v4-pro
- compression: ollama-cloud / deepseek-v4-pro
- vision: nvidia / minimaxai/minimax-m3
- web_extract: nvidia / minimaxai/minimax-m3
- fallback: openai-codex / gpt-5.4 (expires 7/4)

### Cheap (example-comms-profile, example-forge-profile, example-light-profile)
- main: ollama-cloud / deepseek-v4-flash
- compression: ollama-cloud / deepseek-v4-flash
- vision: nvidia / minimaxai/minimax-m3
- web_extract: nvidia / minimaxai/minimax-m3
- fallback: openai-codex / gpt-5.4 (expires 7/4)

## Cutover procedure

### Step 1: Apply profile configs
Use `scripts/apply_tier_routing.py` to patch all 9 config.yaml files in one pass. The script reads the tier plan and applies main model, compression, vision, web_extract, and utility aux slots.

### Step 2: Update helper scripts
- `model_router.py`: update candidate lists to match tier plan, fix latency scoring
- `provider_watchdog.py` (BOTH copies): update DOMAIN_PRIMARY_MODELS, DOMAIN_FALLBACK_MODELS, HEALTH_CHECK_MODELS, PROFILES
- `router_integration.py`: verify it still works with updated router

### Step 3: Update model-routing skill
- Replace "Current operating model" section with tier plan
- Update auxiliary recommendation section
- Sync master to all 7 profile copies (sha256 verify)

### Step 4: Verify
- Run router in JSON mode for each task type
- Run watchdog in --check-only mode
- Verify all profile configs with read-back script

## 7/4 cutover to Nous

When the provider changes from ollama-cloud to Nous for premium:
1. Update profile configs: `model.provider` and `auxiliary.compression.provider` for premium profiles only
2. Update `model_router.py` candidate lists: change premium candidates from ollama-cloud to nous
3. Update `provider_watchdog.py` DOMAIN_PRIMARY_MODELS: note the new provider
4. Update model-routing SKILL.md "current operating model" section
5. Re-sync SKILL.md to all 7 profile copies

## Watchdog alignment rule

The Provider Health Watchdog is a separate operational layer from the routing policy. When the routing plan changes materially, update all three together in the same turn:
1. Profile configs
2. Helper scripts (model_router.py, provider_watchdog.py BOTH copies, router_integration.py)
3. Model-routing skill (master + 7 profile copies)

Failing to update all three together causes drift: the skill teaches one policy, the watchdog restores another, and cron silently undoes intended changes.

## Overlap map

| Layer | Files | Owner |
|-------|-------|-------|
| Profile configs | 9 config.yaml files | sirvir (direct edit) |
| Router | model_router.py, router_integration.py | sirvir (inherited) |
| Watchdog | provider_watchdog.py (2 copies) | sirvir (inherited) |
| Routing skill | model-routing SKILL.md (master + 7 copies) | sirvir (inherited) |
| Policy | brain/0_Admin/fleet-routing-and-compression-policy-2026-06-28.md | sirvir (authoritative) |
