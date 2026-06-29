#!/usr/bin/env python3
'''
Provider Health Watchdog — conservative provider-outage detector.

Policy after 2026-06-29 update (tier plan beta):
- A single model 503 / "temporarily overloaded" is MODEL-level degradation, not a
  provider outage. Alert only; do not rewrite configs.
- Require multiple consecutive provider-level failures before switching.
- Health-check more than one Ollama model, including the actual default (glm-5.2).
- If fallback is truly needed, use the configured conservative fallback model
  (openai-codex:gpt-5.4), not gpt-5.5.
- When Ollama recovers, restore both provider AND model.default.

Tier plan (beta: ollama-cloud substitutes for Nous until 7/4 cutover):
- Premium profiles (default, maf, research): primary = glm-5.2
- Default profiles (rollout-auto, sirvir, garry-builds): primary = deepseek-v4-pro
- Cheap profiles (comms, forge-frame, personal): primary = deepseek-v4-flash
- Fallback for all profiles: openai-codex / gpt-5.4 (expires 7/4)
- After 7/4 cutover: premium text lanes move to Nous, watchdog will be updated again.

Authoritative policy: ~/.hermes/profiles/sirvir/skills/sirvir/brain/0_Admin/fleet-routing-and-compression-policy-2026-06-28.md

Run manually:
    HERMES_HOME=~/.hermes python3 ~/.hermes/profiles/sirvir/skills/sirvir/scripts/provider_watchdog.py --check-only
'''
import json
import os
import sys
import time
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from datetime import datetime, timezone

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
STATE_PATH = HERMES_HOME / "provider_watchdog_state.json"

PRIMARY_PROVIDER = "ollama-cloud"
FALLBACK_PROVIDER = "openai-codex"
HEALTH_CHECK_MODELS = ["glm-5.2", "minimax-m3", "deepseek-v4-flash"]
HEALTH_CHECK_URL = "https://ollama.com/v1/chat/completions"
FAILURES_BEFORE_SWITCH = 3

# Primary (ollama-cloud) models per profile.
# Tier plan (beta: ollama-cloud substitutes for Nous until 7/4 cutover):
# - Premium (default, maf, research) -> glm-5.2
# - Default (rollout-auto, sirvir, garry-builds) -> deepseek-v4-pro
# - Cheap (comms, forge-frame, personal) -> deepseek-v4-flash
# After 7/4 cutover: premium text lanes move to Nous, update this map.
DOMAIN_PRIMARY_MODELS = {
    "": "glm-5.2",
    "maf": "glm-5.2",
    "research": "glm-5.2",
    "rollout-auto": "deepseek-v4-pro",
    "sirvir": "deepseek-v4-pro",
    "garry-builds": "deepseek-v4-pro",
    "comms": "deepseek-v4-flash",
    "forge-frame": "deepseek-v4-flash",
    "personal": "deepseek-v4-flash",
}

# Fallback (openai-codex) models per profile.
# All profiles use gpt-5.4 as fallback (expires 7/4).
DEFAULT_FALLBACK_MODEL = "gpt-5.4"
DOMAIN_FALLBACK_MODELS = {
    "": "gpt-5.4",
    "maf": "gpt-5.4",
    "rollout-auto": "gpt-5.4",
    "sirvir": "gpt-5.4",
    "garry-builds": "gpt-5.4",
    "personal": "gpt-5.4",
    "research": "gpt-5.4",
    "comms": "gpt-5.4",
    "forge-frame": "gpt-5.4",
}

PROFILES = [
    "",
    "maf",
    "research",
    "rollout-auto",
    "sirvir",
    "garry-builds",
    "comms",
    "forge-frame",
    "personal",
]


def load_env_key(name):
    env_path = HERMES_HOME / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return None


def load_state():
    default = {
        "current_provider": PRIMARY_PROVIDER,
        "failures": 0,
        "last_check": None,
        "last_switch": None,
        "last_classification": None,
    }
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text())
            default.update(state)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def classify_error(status_code, error_text):
    text = (error_text or "").lower()
    if "temporarily overloaded" in text or "model" in text and "overloaded" in text:
        return "model_overloaded"
    if status_code == 429:
        return "quota_exhausted"
    if status_code and 500 <= status_code <= 599:
        return "provider_5xx"
    if "timed out" in text or "connection error" in text:
        return "provider_unreachable"
    return "unknown_failure"


def ping_ollama_model(api_key, model):
    try:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            HEALTH_CHECK_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        latency = round(time.perf_counter() - start, 3)
        return {
            "model": model,
            "healthy": True,
            "latency_s": latency,
            "status_code": 200,
            "error": None,
            "classification": "healthy",
        }

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")[:500]
        except Exception:
            pass
        error = f"HTTP {e.code}: {body}"
        return {
            "model": model,
            "healthy": False,
            "latency_s": None,
            "status_code": e.code,
            "error": error,
            "classification": classify_error(e.code, error),
        }
    except urllib.error.URLError as e:
        error = f"Connection error: {e.reason}"
        return {
            "model": model,
            "healthy": False,
            "latency_s": None,
            "status_code": None,
            "error": error,
            "classification": classify_error(None, error),
        }
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        return {
            "model": model,
            "healthy": False,
            "latency_s": None,
            "status_code": None,
            "error": error,
            "classification": classify_error(None, error),
        }


def check_ollama_health(api_key):
    results = [ping_ollama_model(api_key, model) for model in HEALTH_CHECK_MODELS]
    healthy_results = [r for r in results if r["healthy"]]
    if healthy_results:
        return {
            "healthy": True,
            "classification": "healthy",
            "results": results,
            "latency_s": healthy_results[0]["latency_s"],
            "error": None,
        }

    classes = {r["classification"] for r in results}
    # All failures are model-level overloads: provider can still be alive; do not switch.
    if classes == {"model_overloaded"}:
        classification = "model_overloaded"
    elif "quota_exhausted" in classes:
        classification = "quota_exhausted"
    elif classes & {"provider_5xx", "provider_unreachable"}:
        classification = "provider_failure"
    else:
        classification = "unknown_failure"

    return {
        "healthy": False,
        "classification": classification,
        "results": results,
        "latency_s": None,
        "error": "; ".join(f"{r['model']}: {r['error']}" for r in results),
    }


def hermes_config_set(profile, key, value):
    env = os.environ.copy()
    env["HERMES_HOME"] = str(HERMES_HOME)
    args = ["hermes", "config", "set", key, value]
    if profile:
        args = ["hermes", "--profile", profile, "config", "set", key, value]
    result = subprocess.run(args, capture_output=True, text=True, timeout=20, env=env)
    if result.returncode != 0:
        print(f"  FAILED ({profile or 'default'}): {result.stderr.strip() or result.stdout.strip()}")
        return False
    return True


def switch_profile(profile, provider, model):
    ok_provider = hermes_config_set(profile, "model.provider", provider)
    ok_model = hermes_config_set(profile, "model.default", model) if ok_provider else False
    return ok_provider and ok_model


def main():
    check_only = "--check-only" in sys.argv

    api_key = load_env_key("OLLAMA_API_KEY")
    if not api_key:
        print("ERROR: OLLAMA_API_KEY not found in .env")
        sys.exit(1)

    state = load_state()
    now = datetime.now(timezone.utc).isoformat()

    health = check_ollama_health(api_key)
    state["last_check"] = now
    state["last_classification"] = health["classification"]

    print(f"[{now}] Ollama health check: {'HEALTHY' if health['healthy'] else 'UNHEALTHY'} ({health['classification']})")
    for r in health["results"]:
        status = "OK" if r["healthy"] else r["classification"]
        line = f"  {r['model']}: {status}"
        if r["latency_s"]:
            line += f" latency={r['latency_s']}s"
        if r["error"]:
            line += f" error={r['error']}"
        print(line)

    if health["healthy"]:
        state["failures"] = 0
        if state["current_provider"] == FALLBACK_PROVIDER:
            print(f"\n-> Ollama recovered. Restoring all profiles to {PRIMARY_PROVIDER}...")
            if not check_only:
                for profile in PROFILES:
                    name = profile or "default"
                    primary_model = DOMAIN_PRIMARY_MODELS.get(profile, "deepseek-v4-pro")
                    ok = switch_profile(profile, PRIMARY_PROVIDER, primary_model)
                    print(f"  {'OK' if ok else 'FAIL'} {name} -> {PRIMARY_PROVIDER}:{primary_model}")
                state["current_provider"] = PRIMARY_PROVIDER
                state["last_switch"] = now
                print("-> All profiles restored to ollama-cloud.")
            else:
                print("  (--check-only: would restore profiles)")
        else:
            print(f"  Primary ({PRIMARY_PROVIDER}) healthy. No action needed.")
        save_state(state)

    else:
        # Model overload is not provider failure. Alert only; do not increment toward switch.
        if health["classification"] == "model_overloaded":
            print("\n!! Model-level overload detected. No provider switch. Will retry next tick.")
            save_state(state)
        else:
            state["failures"] += 1
            save_state(state)

            if state["current_provider"] == FALLBACK_PROVIDER:
                print(f"  Already on fallback ({FALLBACK_PROVIDER}). Failure count: {state['failures']}")
            elif state["failures"] < FAILURES_BEFORE_SWITCH:
                remaining = FAILURES_BEFORE_SWITCH - state["failures"]
                print(f"\n!! Provider-level failure #{state['failures']}. No switch yet; need {remaining} more consecutive failure(s).")
            else:
                print(f"\n!! Provider unhealthy for {state['failures']} consecutive checks. Switching to {FALLBACK_PROVIDER}...")
                if not check_only:
                    for profile in PROFILES:
                        name = profile or "default"
                        fallback_model = DOMAIN_FALLBACK_MODELS.get(profile, DEFAULT_FALLBACK_MODEL)
                        ok = switch_profile(profile, FALLBACK_PROVIDER, fallback_model)
                        print(f"  {'OK' if ok else 'FAIL'} {name} -> {FALLBACK_PROVIDER}:{fallback_model}")
                    state["current_provider"] = FALLBACK_PROVIDER
                    state["last_switch"] = now
                    save_state(state)
                    print(f"-> All profiles switched to {FALLBACK_PROVIDER}.")
                else:
                    print("  (--check-only: would switch all profiles)")

    print(
        f"\nState: provider={state['current_provider']} failures={state['failures']} "
        f"classification={state.get('last_classification')} last_switch={state.get('last_switch', 'never')}"
    )


if __name__ == "__main__":
    main()
