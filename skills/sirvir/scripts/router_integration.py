#!/usr/bin/env python3
"""
Router Integration — bridges model_router.py into Hermes agent sessions.

Called by the model-routing skill to dynamically switch models based on task type.
Outputs Hermes-compatible model switch commands and JSON for programmatic use.

Usage from within Hermes:
    python ${HERMES_HOME}/home/router_integration.py --task financial --priority quality
    python ${HERMES_HOME}/home/router_integration.py --prompt "Calculate IRR for..." --priority speed
    python ${HERMES_HOME}/home/router_integration.py --task coding --high-stakes

Output modes:
    --hermes-cmd   → prints "/model openai-codex:gpt-5.5" for direct use
    --json         → prints JSON for programmatic consumption
    --config       → prints "hermes config set model.default <model>" command
    (default)      → human-readable summary
"""
import json
import sys
import argparse
import os
import subprocess
from pathlib import Path

# Import the router
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes" / "data")))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_router import select_model, detect_task_type, load_benchmark


def get_current_model():
    """Read current model from Hermes config."""
    config_path = HERMES_HOME / "config.yaml"
    if not config_path.exists():
        return None, None
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        model = config.get("model", {})
        return model.get("default"), model.get("provider")
    except Exception:
        return None, None


def format_hermes_switch(model: str, provider: str) -> str:
    """Format a /model slash command for Hermes."""
    return f"/model {provider}:{model}"


def format_config_command(model: str, provider: str) -> str:
    """Format a hermes config set command."""
    return f"hermes config set model.default {model} && hermes config set model.provider {provider}"


def main():
    parser = argparse.ArgumentParser(
        description="Router Integration — bridge model_router.py into Hermes"
    )
    parser.add_argument("--task", choices=["financial", "creative", "coding", "operations", "quick", "reasoning", "auto"],
                        help="Task type (or 'auto' to detect from prompt)")
    parser.add_argument("--priority", choices=["speed", "balanced", "cost", "quality"],
                        default="balanced", help="Optimization priority")
    parser.add_argument("--prompt", help="Prompt text (required for --task auto)")
    parser.add_argument("--high-stakes", action="store_true", help="Prefer reliability over cost")
    parser.add_argument("--profile", default="sirvir", help="Profile to classify and route for")
    parser.add_argument("--allow-conservative-fallback", action="store_true", help="Use conservative fallback when evidence is incomplete")
    parser.add_argument("--hermes-cmd", action="store_true", help="Output /model slash command")
    parser.add_argument("--config", action="store_true", help="Output hermes config set command")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--apply", action="store_true", help="Apply the switch immediately via hermes config")
    args = parser.parse_args()

    if not args.task:
        parser.error("--task required")

    model, details = select_model(
        args.task, args.priority, args.prompt, args.high_stakes, args.profile, args.allow_conservative_fallback
    )

    if model is None:
        error = details.get("error", "unknown error")
        if args.json:
            print(json.dumps({"error": error}))
        else:
            print(f"ERROR: {error}")
        sys.exit(1)

    current_model, current_provider = get_current_model()

    if args.hermes_cmd:
        print(format_hermes_switch(model, details["provider"]))
    elif args.config:
        print(format_config_command(model, details["provider"]))
    elif args.json:
        output = dict(details)
        output["current_model"] = current_model
        output["current_provider"] = current_provider
        output["switch_command"] = format_hermes_switch(model, details["provider"])
        output["config_command"] = format_config_command(model, details["provider"])
        print(json.dumps(output, indent=2))
    else:
        print(f"Task Type:     {details['task_type']}")
        print(f"Priority:      {details['priority']}")
        print(f"High Stakes:   {details.get('high_stakes', False)}")
        print(f"Current Model: {current_model or 'unknown'} ({current_provider or 'unknown'})")
        print(f"→ Switch To:   {model} ({details['provider']})")
        print(f"Score:         {details['weighted_score']:.2f}")
        if details['avg_latency_s']:
            print(f"Latency:       {details['avg_latency_s']:.2f}s")
        print(f"Success Rate:  {details['success_rate']}%")
        print(f"Benchmark:     {details['benchmark_age']}")
        if details["alternatives"]:
            print(f"Fallbacks:     {', '.join(a['model'] for a in details['alternatives'])}")
        print()
        print(f"Slash command:  {format_hermes_switch(model, details['provider'])}")
        print(f"Config command: {format_config_command(model, details['provider'])}")

    if args.apply:
        cmd = ["hermes", "config", "set", "model.default", model]
        subprocess.run(cmd, check=False)
        cmd = ["hermes", "config", "set", "model.provider", details["provider"]]
        subprocess.run(cmd, check=False)
        print(f"Applied: model.default={model}, model.provider={details['provider']}")


if __name__ == "__main__":
    main()
