# Provider Fitness by Usage Tier

Use this reference when recommending providers or rewriting routing policy after the 2026-06-30 support-backed NVIDIA review.

## Core finding

NVIDIA NIM should not be treated as a production-default provider for heavy Hermes usage.

The issue is not just occasional failed calls. Under heavy use, rate limiting and response delay can cause aux work to miss its window, after which the main model effectively does the work anyway. That creates a false-economy pattern:
- nominally cheap/free provider
- poor effective aux completion under load
- main model silently absorbs the workload
- worse performance and misleading routing economics

## Recommendation rule

Classify the user or workload before recommending a provider.

### Light user
Typical pattern:
- low request volume
- low concurrency
- low sustained TPS
- mostly casual or intermittent use

Recommendation:
- NVIDIA NIM is acceptable to suggest
- free/experimental lanes are acceptable

### Moderate user
Typical pattern:
- recurring daily use
- some sustained sessions
- a mix of light and serious work

Recommendation:
- NVIDIA NIM is allowed only for light profiles or explicitly low-stakes aux work
- do not present NVIDIA as the default answer across the fleet

### Heavy user
Typical pattern:
- sustained throughput
- long sessions
- high token volume
- production reliance on stable aux behavior

Recommendation:
- do not recommend NVIDIA as the default aux or main provider
- prefer providers that remain reliable under sustained Hermes load

### Corp-level user
Typical pattern:
- multi-profile fleet
- business-critical uptime
- routing decisions have organization-wide impact

Recommendation:
- exclude NVIDIA from default production recommendations
- only mention it as experimental/light-duty

## Evidence hierarchy for classification

Use these in order when available:
1. historical token/session data from state.db
2. observed workload shape across profiles
3. provider/dashboard usage snapshots
4. direct user statement about expected usage level

## Wording rule

Do not frame NVIDIA as "the free default" without qualification.

Instead say one of:
- "good for light-use / experimental workloads"
- "not my production recommendation for heavy Hermes usage"
- "acceptable for light profiles, not for fleet-default routing"

## Scope note

This reference changes recommendation policy, routing guidance, and skill text.
It does not by itself require changes to local turbofit strategy, benchmark methodology, or budget math.
