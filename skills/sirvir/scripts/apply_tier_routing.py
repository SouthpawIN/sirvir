#!/usr/bin/env python3
"""
Apply fleet tier routing to all profile config.yaml files.

Usage:
    python3 apply_tier_routing.py [--dry-run] [--provider ollama-cloud|nous]

Defaults to ollama-cloud (beta provider). Use --provider nous for post-beta cutover.

Reads the tier assignments from TIERS below and patches:
- model.provider, model.default, model.base_url
- auxiliary.vision, web_extract, compression, skills_hub, approval, mcp, title_generation

Does NOT touch: fallback_providers, compression settings, kanban, prompt_caching, etc.
"""
import yaml
from pathlib import Path
import argparse

# ── Tier assignments ──────────────────────────────────────────────────
TIERS = {
    "default":      "premium",
    "maf":          "premium",
    "research":     "premium",
    "rollout-auto": "default",
    "sirvir":       "default",
    "garry-builds": "default",
    "comms":        "cheap",
    "forge-frame":  "cheap",
    "personal":     "cheap",
}

MAIN_PER_TIER = {
    "premium": "glm-5.2",
    "default": "deepseek-v4-pro",
    "cheap":   "deepseek-v4-flash",
}

VISION_PROVIDER = "nvidia"
VISION_MODEL = "minimaxai/minimax-m3"

CONFIG_PATHS = {
    "default":      Path("~/.hermes/config.yaml"),
    "maf":          Path("~/.hermes/profiles/maf/config.yaml"),
    "research":     Path("~/.hermes/profiles/research/config.yaml"),
    "rollout-auto": Path("~/.hermes/profiles/rollout-auto/config.yaml"),
    "sirvir":       Path("~/.hermes/profiles/sirvir/config.yaml"),
    "garry-builds": Path("~/.hermes/profiles/garry-builds/config.yaml"),
    "comms":        Path("~/.hermes/profiles/comms/config.yaml"),
    "forge-frame":  Path("~/.hermes/profiles/forge-frame/config.yaml"),
    "personal":     Path("~/.hermes/profiles/personal/config.yaml"),
}


def apply_tier_routing(provider="ollama-cloud", dry_run=False):
    changes_log = []
    
    for profile_name, tier in TIERS.items():
        config_path = CONFIG_PATHS[profile_name]
        if not config_path.exists():
            changes_log.append(f"SKIP {profile_name}: config not found at {config_path}")
            continue
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        main_model = MAIN_PER_TIER[tier]
        changes = []
        
        # Fix model.provider
        old_provider = config.get("model", {}).get("provider", "")
        if old_provider != provider:
            config.setdefault("model", {})["provider"] = provider
            changes.append(f"model.provider: {old_provider} -> {provider}")
        
        # Fix model.default
        old_model = config.get("model", {}).get("default", "")
        if old_model != main_model:
            config.setdefault("model", {})["default"] = main_model
            changes.append(f"model.default: {old_model} -> {main_model}")
        
        # Remove stale codex base_url
        old_base_url = config.get("model", {}).get("base_url", "")
        if old_base_url and "chatgpt.com" in str(old_base_url):
            config["model"]["base_url"] = ""
            changes.append(f"model.base_url: stale codex URL -> ''")
        
        # Set auxiliary slots
        aux = config.setdefault("auxiliary", {})
        
        # Vision and web_extract -> nvidia/minimax-m3
        for task in ["vision", "web_extract"]:
            task_cfg = aux.setdefault(task, {})
            old_p = task_cfg.get("provider", "")
            old_m = task_cfg.get("model", "")
            if old_p != VISION_PROVIDER or old_m != VISION_MODEL:
                task_cfg["provider"] = VISION_PROVIDER
                task_cfg["model"] = VISION_MODEL
                changes.append(f"aux.{task}: {old_p}/{old_m} -> {VISION_PROVIDER}/{VISION_MODEL}")
        
        # Compression -> tier main model on the text provider
        comp_cfg = aux.setdefault("compression", {})
        old_cp = comp_cfg.get("provider", "")
        old_cm = comp_cfg.get("model", "")
        if old_cp != provider or old_cm != main_model:
            comp_cfg["provider"] = provider
            comp_cfg["model"] = main_model
            changes.append(f"aux.compression: {old_cp}/{old_cm} -> {provider}/{main_model}")
        
        # Utility aux slots -> nvidia/minimax-m3
        for task in ["skills_hub", "approval", "mcp", "title_generation"]:
            task_cfg = aux.setdefault(task, {})
            old_p = task_cfg.get("provider", "")
            old_m = task_cfg.get("model", "")
            if old_p != VISION_PROVIDER or old_m != VISION_MODEL:
                task_cfg["provider"] = VISION_PROVIDER
                task_cfg["model"] = VISION_MODEL
                changes.append(f"aux.{task}: {old_p}/{old_m} -> {VISION_PROVIDER}/{VISION_MODEL}")
        
        if not dry_run:
            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        if changes:
            changes_log.append(f"\n=== {profile_name} ({tier}) {'[DRY RUN]' if dry_run else '[APPLIED]'} ===")
            for c in changes:
                changes_log.append(f"  {c}")
        else:
            changes_log.append(f"\n=== {profile_name} ({tier}) === NO CHANGES NEEDED")
    
    return "\n".join(changes_log)


def verify():
    """Read back all configs and verify tier routing is correct."""
    all_ok = True
    print(f"{'PROFILE':<14} {'TIER':<8} {'MAIN':<22} {'VISION':<30} {'COMP':<22} {'STATUS'}")
    print("-" * 120)
    
    for name, tier in TIERS.items():
        config_path = CONFIG_PATHS[name]
        if not config_path.exists():
            print(f"{name:<14} {tier:<8} {'MISSING':<22} {'':<30} {'':<22} FAIL")
            all_ok = False
            continue
        
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        
        m = cfg.get("model", {})
        aux = cfg.get("auxiliary", {})
        
        main_provider = m.get("provider", "")
        main_model = m.get("default", "")
        v = aux.get("vision", {})
        c = aux.get("compression", {})
        
        exp_main = MAIN_PER_TIER[tier]
        ok = True
        issues = []
        
        if main_model != exp_main:
            ok = False; issues.append(f"main={main_model} expected {exp_main}")
        if (v.get("provider"), v.get("model")) != (VISION_PROVIDER, VISION_MODEL):
            ok = False; issues.append(f"vision mismatch")
        if c.get("model") != exp_main:
            ok = False; issues.append(f"comp={c.get('model')} expected {exp_main}")
        
        status = "OK" if ok else f"FAIL: {', '.join(issues)}"
        if not ok:
            all_ok = False
        
        vp_vm = f"{v.get('provider','')}/{v.get('model','')}"
        cp_cm = f"{c.get('provider','')}/{c.get('model','')}"
        print(f"{name:<14} {tier:<8} {main_provider+'/'+main_model:<22} {vp_vm:<30} {cp_cm:<22} {status}")
    
    print()
    print("ALL CONFIGS VERIFIED" if all_ok else "VERIFICATION FAILED")
    return all_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply fleet tier routing to all profiles")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--provider", default="ollama-cloud", choices=["ollama-cloud", "nous"], 
                        help="Text-lane provider (beta: ollama-cloud, post-beta: nous)")
    parser.add_argument("--verify", action="store_true", help="Verify configs only, no changes")
    args = parser.parse_args()
    
    if args.verify:
        verify()
    else:
        result = apply_tier_routing(provider=args.provider, dry_run=args.dry_run)
        print(result)
        print("\n--- Verification ---")
        verify()