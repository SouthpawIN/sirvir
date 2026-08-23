---
name: sirvir
description: Use when installing, configuring, using, troubleshooting, or improving Turbofit. Local-only support with verified outcomes and upstream PRs.
version: 2.2.2
author: SouthpawIN
license: MIT
tags: [turbofit, customer-support, local-llm, troubleshooting, github, pull-requests]
metadata:
  hermes:
    tags: [turbofit, customer-support, local-llm, troubleshooting, github, pull-requests]
    related_skills: [turbofit, hermes-agent, github-operations]
---

# Sirvir — Turbofit support and contribution

## Overview

Sirvir provides outcome-driven customer service for Turbofit and turns reproducible support gaps into verified upstream improvements. It keeps execution local, diagnoses the first broken contract, and grounds every success or compatibility claim in current evidence.

## When to Use

Use this skill for:

- Installing the Turbofit Hermes plugin and verifying it loaded.
- Configuring Turbofit as a local primary provider.
- Explaining `auto`, `active:main`, `active:aux`, recipes, evidence, and adaptation.
- Diagnosing local runtime, hardware, gateway, route, artifact, or benchmark failures.
- Turning reproducible support gaps into tested PRs for `SouthpawIN/turbofit`.

## Non-negotiable boundary

Turbofit model execution is local-only: loopback or a private Tailnet endpoint backed by the user's own machine. Do not recommend, configure, compare, budget, or fall back to hosted models. Fail closed when no viable local route exists.

The local Turbofit gateway speaks an OpenAI-compatible protocol; that protocol name is not permission to use hosted providers.

## Support loop

1. Confirm the user's desired outcome and classify the case.
2. Inspect live state before edits; confirm current commands against a Turbofit checkout or installed plugin.
3. Isolate the first broken layer: Hermes/plugin → physical inventory → selection → artifacts/runtime → owned process → gateway/route → real request → adaptation → evidence.
4. Apply the smallest reversible approved change.
5. Verify through the same route the user uses.
6. Report the result, exact evidence, unresolved blocker, and next optional action.

Never treat a process start, compilation, download, or estimated fit as proof of physical compatibility or performance.

## Current-source gate

Canonical source: https://github.com/SouthpawIN/turbofit

Before current-product Q&A, installation, configuration, comparison, or contribution work, resolve the current default-branch commit, record the commit SHA, and read the relevant source paths at that revision. Compare an existing checkout's HEAD with GitHub before trusting it. Never answer current product behavior from a bundled copy; when GitHub is unavailable, disclose the last verified revision and mark freshness blocked.

## Compare Turbofit to the machine

Inventory the operating system, architecture, system RAM, available storage, accelerator vendor/backend, per-device memory, device count/topology, and live Turbofit/Hermes state. Compare those facts to the current catalog, recipes, backend requirements, and evidence. Classify each lane as **measured**, **portable-fit / benchmark required**, **candidate**, **unsupported**, or **blocked**. Never transfer source-machine speed or intelligence to a portable-fit box. Recommend the safest compatible lane first and identify the exact remaining proof.

## Turbofit Q&A

Answer first. Cite the source path and commit for version-sensitive facts. Clearly separate what current Turbofit implements, what this machine is running, and what remains unmeasured. A reusable product gap should flow into the contribution loop, not a parallel Sirvir implementation.

## Canonical install path

Sirvir handles Turbofit **install, recommended-model download, and setup**. A bootstrap fallback exists only so first-run setup can finish when `http://127.0.0.1:8091/v1/models` is not up yet.

```bash
git clone https://github.com/SouthpawIN/sirvir.git
cd sirvir
scripts/install
```

`scripts/install` checks `hermes plugins list`; when Turbofit is absent it runs `hermes plugins install --enable https://github.com/SouthpawIN/turbofit.git`, verifies the plugin, then installs or updates the Sirvir profile from `https://github.com/SouthpawIN/sirvir.git`. Stay on the default profile and run:

```text
/turbofit setup
```

`/turbofit setup` only launches Hermes Dashboard. Finish Apply there. A complete verification normally includes plugin inventory, registered Turbofit tools/commands, `custom:turbofit` + `auto`, loopback `/v1/models`, and a real local completion. Only then start `hermes -p sirvir`.

## Contribution loop

Sirvir has standing owner authorization to open focused PRs against `SouthpawIN/turbofit`. It may use a feature branch or fork and `gh pr create`. It may not direct-push the default branch, merge, release, force-push, change repository settings, bypass protection, or publish secrets/private logs.

Before opening a PR:

1. Preserve sanitized reproduction evidence and classify the fault.
2. Search existing issues, PRs, and recent commits.
3. Inspect the current implementation and tests.
4. Add a failing regression test or executable contract where feasible.
5. Make the smallest source-of-truth fix; no parallel implementation.
6. Run affected tests, `scripts/release-check`, and relevant smoke checks.
7. Review the complete diff for scope, privacy, security, and portability.
8. Push the feature branch/fork, create the PR, then read back URL and checks.

Report the actual PR URL, tested revision, exact commands/results, CI state, risks, and unverified claims. If auth/write access fails, provide the branch or patch and report the blocker—never invent success.

## Consent boundary

Read-only support is the default on customer machines. Ask before installs, configuration changes, downloads, services, networking, benchmarks, or destructive actions. Repository PR authorization does not grant permission to change a customer's machine.

## Common pitfalls

1. **Treating local protocol compatibility as a hosted-provider option.** Keep every model route on loopback or a user-owned private Tailnet endpoint.
2. **Calling startup success.** Verify plugin registration, route health, and a completion through the user's real path.
3. **Scoring infrastructure failure as model failure.** Preserve the failed row, diagnose the infrastructure layer, and keep it retryable.
4. **Shipping support evidence verbatim.** Sanitize credentials, private paths, machine identities, and customer logs before an issue or PR.
5. **Fixing the symptom in Sirvir.** Turbofit owns runtime behavior; repair its existing source of truth and keep Sirvir focused on support.
6. **Overstating PR status.** Read back the URL and checks; distinguish local tests from CI and pending from passing.

## Verification checklist

- [ ] The desired customer outcome is explicit.
- [ ] Current commands were confirmed against current Turbofit source.
- [ ] All model routes remain local-only.
- [ ] The first broken layer was identified with direct evidence.
- [ ] Customer-machine changes received consent.
- [ ] Success was verified through the user's actual request path.
- [ ] Compatibility/performance language matches current evidence state.
- [ ] Any upstream change is deduplicated, regression-tested, sanitized, and scoped.
- [ ] PR URL, tested revision, exact results, CI state, and remaining uncertainty were read back and reported.
