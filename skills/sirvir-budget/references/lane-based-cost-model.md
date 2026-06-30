# Lane-based Cost Model

Use this reference when reconstructing or explaining the budget model after the three-tier routing split.

## Core routing split

The fleet routing policy (2026-06-28) defines three tiers, not two:

### Premium tier
- primary: GLM 5.2 (via Nous)
- alternate premium reasoning lane: Qwen 3.7 MAX (via Nous)

Use premium for:
- high-stakes reasoning
- harder coding
- tasks where quality clearly outweighs cost
- orchestrator profiles whose mistakes cascade downstream

### Default tier
- primary: DeepSeek V4 Pro (via Nous post-7/4, ollama-cloud during beta)
- This is the smart middle lane — good quality without premium-by-default cost

Use default for:
- serious production work
- infra/model management
- implementation lanes needing good reasoning

### Cheap tier
- primary: DeepSeek V4 Flash (via ollama-cloud during beta)
- primary vision/aux: MiniMax M3 (via NVIDIA NIM, free)

Use cheap for:
- routine reasoning
- lower-stakes tasks
- high-volume coordination/admin work
- most vision/aux tasks
- example-comms-profile, formatting, low-stakes drafting

## Cost-model consequence

With this three-tier split, the budget model is:

- **Cheap-tier traffic is effectively free** when it stays on NIM (vision/aux) or DeepSeek V4 Flash (text)
- **Default-tier traffic is low-cost** — DeepSeek V4 Pro is materially cheaper than GLM 5.2
- **Premium-tier traffic is the primary spend driver** — GLM 5.2 at $0.95/$3.00 per 1M tokens

This means monthly spend is governed mainly by:
1. premium-tier share (what fraction of total traffic hits GLM 5.2)
2. default-tier share (what fraction hits DeepSeek V4 Pro vs free Flash)
3. cache reuse / effective cost per 1M tokens

## Why the budget ladder still works

The preserved ladder was:
- optimistic: $0.11 / 1M
- base: $0.125 / 1M
- conservative: $0.14 / 1M

That ladder only remains plausible if:
- a large fraction of traffic stays on the free cheap tier (NIM + Flash)
- default-tier usage is moderate
- premium usage is selective rather than default
- caching is materially better than the pre-upgrade baseline

## Practical interpretation

- If premium share stays under ~30%, the fleet is more likely to remain near the healthy/base budget band.
- If premium share rises into the 40-50% range, cost pressure will drift toward the conservative band.
- If premium share rises above 50%, cost pressure will exceed the conservative band.
- If default-tier share is high but premium is low, costs stay moderate.
- If Qwen 3.7 MAX becomes the default premium lane instead of GLM 5.2, cost pressure rises because Qwen is the more expensive premium option ($1.25/$3.75 vs $0.95/$3.00).

### Empirically verified constraint (2026-06-29 cost spectrum)

Live fleet data (820M tokens across 9 profiles) confirmed:

- **At 90% premium share and 28% cache rate, effective cost is $0.70/1M** — 5× the $0.125/1M planning base and 5× the $0.14/1M conservative band.
- **The planning bands ($0.11-$0.14/1M) require BOTH premium share <30% AND cache rate >70%.** Either condition alone is insufficient — premium share at 30% with 28% cache still produces ~$0.30/1M effective.
- **The root "default" profile is the dominant cost driver.** At 614M tokens (75% of fleet), moving it from premium to default tier saves $181/month — the single largest lever.
- **Cache is the multiplier.** Closing the cache gap from 28% to 80% on the root profile alone saves ~$297/month at GLM 5.2 pricing — more than the tier-downgrade savings.

When modeling costs, always compute the effective rate from live data rather than assuming the planning bands. The bands are targets, not guarantees.

## Recommended default reading of the three-tier split

For budget reasoning, assume:
- GLM 5.2 = standard premium lane (highest cost, highest quality)
- DeepSeek V4 Pro = default middle lane (moderate cost, good quality)
- DeepSeek V4 Flash = cheap text lane (lowest cost, acceptable quality)
- MiniMax M3 = free vision/aux lane (zero cost, good multimodal)

## Decision rule

When explaining why spend changed, separate the causes:
1. Did premium-tier share rise?
2. Did default-tier share rise (pushing more traffic off the free cheap lane)?
3. Did cache performance worsen?
4. Did vision/aux work drift off free MiniMax/NIM routing?

Do not explain spend growth from raw token volume alone when the routing mix changed materially.

## Profile-to-tier mapping (from fleet policy, updated 2026-06-29)

| Profile | Tier | Main Model | Compression |
|---------|------|-----------|-------------|
| research | Premium | GLM 5.2 | GLM 5.2 |
| default | Default | DeepSeek V4 Pro | DeepSeek V4 Pro |
| example-maf-profile | Default | DeepSeek V4 Pro | DeepSeek V4 Pro |
| example-rollout-profile | Default | DeepSeek V4 Pro | DeepSeek V4 Pro |
| sirvir | Default | DeepSeek V4 Pro | DeepSeek V4 Pro |
| example-builds-profile | Default | DeepSeek V4 Pro | DeepSeek V4 Pro |
| example-comms-profile | Cheap | DeepSeek V4 Flash | DeepSeek V4 Flash |
| example-forge-profile | Cheap | DeepSeek V4 Flash | DeepSeek V4 Flash |
| example-light-profile | Cheap | DeepSeek V4 Flash | DeepSeek V4 Flash |

All profiles use NVIDIA/MiniMax M3 for vision and web_extract regardless of tier.

**Change log (2026-06-29):** default and example-maf-profile downgraded from Premium to Default after cost spectrum analysis showed 90% premium share was 5× the budget target. Research remains the only premium profile. See `references/cost-spectrum.md` for the full analysis.
