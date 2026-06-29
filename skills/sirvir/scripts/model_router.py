#!/usr/bin/env python3
"""
Model Router — dynamic model selection based on task type, priority, and live benchmark data.

Usage:
    python ~/.hermes/profiles/sirvir/skills/sirvir/model_router.py --task financial --priority speed
    python ~/.hermes/profiles/sirvir/skills/sirvir/model_router.py --task coding --priority quality --json
    python ~/.hermes/profiles/sirvir/skills/sirvir/model_router.py --prompt "Write brand voice for..." --priority quality
    python ~/.hermes/profiles/sirvir/skills/sirvir/model_router.py --list

Files:
    ~/.hermes/profiles/sirvir/skills/sirvir/benchmark_fast_results.json — live benchmark data (monthly cron)
    ~/.hermes/profiles/sirvir/skills/sirvir/model_routing_matrix.md — human-readable routing report

Tier plan (beta: ollama-cloud substitutes for Nous until 7/4 cutover):
    Premium: ollama-cloud / glm-5.2 (main + compression)
    Default: ollama-cloud / deepseek-v4-pro (main + compression)
    Cheap:   ollama-cloud / deepseek-v4-flash (main + compression)
    Vision + web_extract: nvidia / minimax-m3 (all tiers, NIM free)
    Fallback: openai-codex / gpt-5.4 (all tiers, expires 7/4)

Authoritative policy: ~/.hermes/profiles/sirvir/skills/sirvir/brain/0_Admin/fleet-routing-and-compression-policy-2026-06-28.md
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("~/.hermes/profiles/sirvir/skills/sirvir")
BENCHMARK_PATH = ROOT / "benchmark_fast_results.json"
MATRIX_PATH = ROOT / "model_routing_matrix.md"

# ── Task type detection from prompt keywords ──────────────────────────
TASK_KEYWORDS = {
    "financial": [
        "revenue", "ebitda", "irr", "valuation", "cash flow", "profit",
        "investment", "acquisition", "cap rate", "amortization", "depreciation",
        "balance sheet", "income statement", "npv", "roi", "margin",
    ],
    "creative": [
        "brand voice", "email", "headline", "copy", "marketing", "social media",
        "tagline", "messaging", "positioning", "pitch", "outreach", "campaign",
        "blog post", "press release", "newsletter",
    ],
    "coding": [
        "function", "algorithm", "debug", "refactor", "api", "class",
        "implement", "code", "script", "module", "library", "framework",
        "deploy", "ci/cd", "docker", "test", "bug", "fix",
    ],
    "operations": [
        "schedule", "dispatch", "optimize", "capacity", "logistics",
        "routing", "fleet", "inventory", "workflow", "pipeline",
    ],
    "quick": [
        "what is", "calculate", "convert", "capital of", "define",
        "how many", "when did", "who is", "translate",
    ],
    "reasoning": [
        "analyze", "compare", "should i", "strategy", "pros and cons",
        "evaluate", "assess", "recommend", "trade-off", "decision",
    ],
}

# ── Priority weights ──────────────────────────────────────────────────
PRIORITY_WEIGHTS = {
    "speed":    {"latency": 0.60, "quality": 0.25, "cost": 0.15},
    "balanced": {"latency": 0.33, "quality": 0.34, "cost": 0.33},
    "cost":     {"latency": 0.15, "quality": 0.25, "cost": 0.60},
    "quality":  {"latency": 0.10, "quality": 0.70, "cost": 0.20},
}

# ── Provider cost tiers (lower = cheaper) ─────────────────────────────
PROVIDER_COST_TIER = {
    "ollama": 1,
    "ollama-cloud": 1,
    "openai-codex": 3,
    "openai": 4,
    "deepseek": 2,
    "copilot": 2,
}

# ── Quality baseline scores (pre-benchmark fallback) ──────────────────
QUALITY_BASELINE = {
    "gpt-5.5": 9.5,
    "gpt-5.4": 9.0,
    "gpt-5.4-mini": 8.0,
    "deepseek-v4-pro": 9.0,
    "deepseek-v3.2": 8.5,
    "glm-5": 8.0,
    "glm-5.1": 8.2,
    "glm-5.2": 8.5,
    "kimi-k2:1t": 8.5,
    "kimi-k2.7-code": 8.5,
    "minimax-m3": 8.0,
    "minimax-m2.7": 7.8,
    "minimax-m2.5": 7.5,
    "minimax-m3": 8.0,
    "minimax-m2.1": 7.0,
    "qwen3-coder:480b": 8.5,
    "gemma4:31b": 7.0,
}


def load_benchmark():
    """Load live benchmark results. Returns None if unavailable."""
    if not BENCHMARK_PATH.exists():
        return None
    try:
        return json.loads(BENCHMARK_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def detect_task_type(prompt: str) -> str:
    """Auto-detect task type from prompt keywords."""
    prompt_lower = prompt.lower()
    scores = {}
    for task, keywords in TASK_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        if score > 0:
            scores[task] = score
    if not scores:
        return "reasoning"
    return max(scores, key=scores.get)


# Provider name normalization: benchmark uses "ollama", config uses "ollama-cloud"
PROVIDER_ALIASES = {
    "ollama": "ollama-cloud",
    "ollama-cloud": "ollama-cloud",
    "openai": "openai-codex",
    "openai-codex": "openai-codex",
}


def _normalize_provider(name: str) -> str:
    return PROVIDER_ALIASES.get(name, name)


def get_benchmark_scores(benchmark_data):
    """Extract per-model scores from benchmark data, keyed by (provider, model, category)."""
    scores = {}
    if not benchmark_data:
        return scores
    for cat, cat_models in benchmark_data.get("by_category", {}).items():
        for entry in cat_models:
            provider = _normalize_provider(entry["provider"])
            key = (provider, entry["model"], cat)
            scores[key] = {
                "success_rate": entry["success_rate"],
                "avg_latency_s": entry.get("avg_latency_s"),
            }
    return scores


def score_model(provider, model, task_type, priority, benchmark_scores):
    """Compute weighted score. Returns None if model is unavailable."""
    bm = benchmark_scores.get((provider, model, task_type), {})
    success_rate = bm.get("success_rate", 100.0)
    avg_latency = bm.get("avg_latency_s")

    if success_rate == 0.0:
        return None

    weights = PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["balanced"])

    if avg_latency is not None:
        # Logarithmic latency curve: 0s=10, 1s=8.1, 3s=5.9, 5s=4.4, 10s=2.3, 30s=0.3
        # This preserves differentiation between models at all latency ranges
        # instead of clamping everything above 3.3s to the same floor.
        latency_score = max(0.5, min(10.0, 10.0 - 2.5 * (avg_latency ** 0.5)))
    else:
        latency_score = 5.0

    quality_score = QUALITY_BASELINE.get(model, 7.0)
    cost_tier = PROVIDER_COST_TIER.get(provider, 3)
    cost_score = max(1.0, 10.0 - (cost_tier - 1) * 3.0)

    weighted = (
        weights["latency"] * latency_score +
        weights["quality"] * quality_score +
        weights["cost"] * cost_score
    )

    return {
        "model": model,
        "provider": provider,
        "latency_score": round(latency_score, 2),
        "quality_score": round(quality_score, 2),
        "cost_score": round(cost_score, 2),
        "weighted_score": round(weighted, 2),
        "avg_latency_s": avg_latency,
        "success_rate": success_rate,
    }


def select_model(task_type, priority="balanced", prompt=None, high_stakes=False):
    """Select the best model for a task.

    Returns (model_name, details_dict) or (None, error_dict).
    """
    if task_type == "auto":
        if not prompt:
            return None, {"error": "prompt required for auto-detection"}
        task_type = detect_task_type(prompt)

    benchmark_data = load_benchmark()
    benchmark_scores = get_benchmark_scores(benchmark_data)

    # Tier-aligned candidates (beta: ollama-cloud replaces Nous until 7/4)
    # Premium main = glm-5.2, Default main = deepseek-v4-pro, Cheap main = deepseek-v4-flash
    # Fallback = openai-codex/gpt-5.4 (expires 7/4)
    candidates = {
        "financial": [
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
        "creative": [
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
        "coding": [
            ("ollama-cloud", "kimi-k2.7-code"),
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "qwen3-coder:480b"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("openai-codex", "gpt-5.4"),
        ],
        "operations": [
            ("ollama-cloud", "deepseek-v4-pro"),
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
        "quick": [
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("openai-codex", "gpt-5.4"),
        ],
        "reasoning": [
            ("ollama-cloud", "glm-5.2"),
            ("ollama-cloud", "deepseek-v4-pro"),
            ("ollama-cloud", "deepseek-v4-flash"),
            ("openai-codex", "gpt-5.4"),
        ],
    }

    models = candidates.get(task_type, candidates["reasoning"])

    scored = []
    for provider, model in models:
        result = score_model(provider, model, task_type, priority, benchmark_scores)
        if result is not None:
            scored.append(result)

    if not scored:
        fallback_candidates = [
            ("openai-codex", "gpt-5.4"),
        ]
        for provider, model in fallback_candidates:
            result = score_model(provider, model, task_type, priority, {})
            if result is not None:
                scored.append(result)

    if not scored:
        return None, {"error": f"No available models for task '{task_type}'."}

    if high_stakes:
        for s in scored:
            if s["provider"] in ("openai-codex", "openai"):
                s["weighted_score"] += 1.0

    scored.sort(key=lambda s: s["weighted_score"], reverse=True)
    winner = scored[0]

    return winner["model"], {
        "model": winner["model"],
        "provider": winner["provider"],
        "task_type": task_type,
        "priority": priority,
        "high_stakes": high_stakes,
        "weighted_score": winner["weighted_score"],
        "latency_score": winner["latency_score"],
        "quality_score": winner["quality_score"],
        "cost_score": winner["cost_score"],
        "avg_latency_s": winner["avg_latency_s"],
        "success_rate": winner["success_rate"],
        "alternatives": [
            {"model": s["model"], "provider": s["provider"], "score": s["weighted_score"]}
            for s in scored[1:4]
        ],
        "benchmark_age": (
            benchmark_data["generated_at"] if benchmark_data else "no benchmark data"
        ),
    }


def list_routing_table():
    """Print full routing table."""
    benchmark_data = load_benchmark()
    benchmark_scores = get_benchmark_scores(benchmark_data)

    print(f"Model Routing Table")
    print(f"Benchmark: {benchmark_data['generated_at'] if benchmark_data else 'NONE — using baselines'}")
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print()

    for task_type in ["financial", "creative", "coding", "operations", "quick", "reasoning"]:
        print(f"## {task_type.title()}")
        print(f"{'Priority':<12} {'Model':<25} {'Provider':<15} {'Score':<8} {'Latency':<10} {'Success':<10}")
        print("-" * 80)
        for priority in ["speed", "balanced", "cost", "quality"]:
            model, details = select_model(task_type, priority)
            if model:
                lat = f"{details['avg_latency_s']:.2f}s" if details['avg_latency_s'] else "N/A"
                print(f"{priority:<12} {model:<25} {details['provider']:<15} {details['weighted_score']:<8.2f} {lat:<10} {details['success_rate']}%")
            else:
                print(f"{priority:<12} {'NO MODEL AVAILABLE':<25} {'—':<15} {'—':<8} {'—':<10} {'—':<10}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Model Router — dynamic model selection")
    parser.add_argument("--task", choices=["financial", "creative", "coding", "operations", "quick", "reasoning", "auto"],
                        help="Task type (or 'auto' to detect from prompt)")
    parser.add_argument("--priority", choices=["speed", "balanced", "cost", "quality"],
                        default="balanced", help="Optimization priority")
    parser.add_argument("--prompt", help="Prompt text (required for --task auto)")
    parser.add_argument("--high-stakes", action="store_true", help="Prefer reliability over cost")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--list", action="store_true", help="Print full routing table")
    args = parser.parse_args()

    if args.list:
        list_routing_table()
        return

    if not args.task:
        parser.error("--task or --list required")

    model, details = select_model(
        args.task, args.priority, args.prompt, args.high_stakes
    )

    if model is None:
        print(json.dumps(details, indent=2) if args.json else f"ERROR: {details.get('error', 'unknown')}")
        sys.exit(1)

    if args.json:
        print(json.dumps(details, indent=2))
    else:
        print(f"Task:      {details['task_type']}")
        print(f"Priority:  {details['priority']}")
        print(f"Model:     {model}")
        print(f"Provider:  {details['provider']}")
        print(f"Score:     {details['weighted_score']:.2f}")
        if details['avg_latency_s']:
            print(f"Latency:   {details['avg_latency_s']:.2f}s")
        print(f"Success:   {details['success_rate']}%")
        if details.get("high_stakes"):
            print(f"Mode:      HIGH-STAKES (reliability premium applied)")
        if details["alternatives"]:
            print(f"Fallbacks: {', '.join(a['model'] for a in details['alternatives'])}")


if __name__ == "__main__":
    main()
