#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("${SIRVIR_SKILL_DIR}")
MODEL_ROUTER_PATH = BASE / "scripts" / "model_router.py"
AUDIT_FLEET_PATH = Path("${SIRVIR_SKILL_DIR}-budget/scripts/audit_fleet.py")
POLICY_PATH = BASE / "references" / "usage-tier-policy.json"
EXAMPLES_PATH = BASE / "references" / "usage-tier-examples.json"
ROOT_CONFIG_PATH = Path("${HERMES_CONFIG}")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def merged_windows(module, raw_windows: dict) -> dict:
    merged = {}
    for label in ("30d", "7d", "24h"):
        base = module._empty_window(label)
        base.update(raw_windows[label])
        merged[label] = base
    return merged


def assert_equal(name: str, actual, expected, failures: list[str]) -> None:
    if actual != expected:
        failures.append(f"{name}: expected {expected!r}, got {actual!r}")


def assert_true(name: str, condition: bool, failures: list[str], detail: str) -> None:
    if not condition:
        failures.append(f"{name}: {detail}")


def invoke_python_json(args: list[str], env: dict[str, str] | None = None, expect_exit: int = 0) -> dict:
    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    if proc.returncode != expect_exit:
        raise RuntimeError(
            f"command {' '.join(args)} exited {proc.returncode}, expected {expect_exit}. stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    return json.loads(proc.stdout)


def run_classification_cases(model_router, policy: dict, examples: dict, failures: list[str]) -> None:
    for case in examples["classification_cases"]:
        windows = merged_windows(model_router, case["windows"])
        result = model_router.classify_usage_tier(windows, policy, scope=case["scope"])
        expected = case["expected"]
        assert_equal(f"{case['name']} tier", result["tier"], expected["tier"], failures)
        if "outlier_detected" in expected:
            assert_equal(f"{case['name']} outlier", result["outlier_detected"], expected["outlier_detected"], failures)
        if "needs_followup" in expected:
            assert_equal(f"{case['name']} needs_followup", result["needs_followup"], expected["needs_followup"], failures)


def make_stub_profile(case: dict, windows: dict, *, aux_provider: str = "ollama-cloud") -> dict:
    return {
        "profile": case["name"],
        "current_main_provider": "ollama-cloud",
        "current_main_model": "deepseek-v4-pro",
        "current_main_lane": "default",
        "current_vision_provider": aux_provider,
        "current_vision_model": "minimax-m3" if aux_provider == "nvidia" else "deepseek-v4-pro",
        "current_auxiliary_slots": {
            "vision": {"provider": aux_provider, "model": "minimax-m3" if aux_provider == "nvidia" else "deepseek-v4-pro"},
            "web_extract": {"provider": aux_provider, "model": "minimax-m3" if aux_provider == "nvidia" else "deepseek-v4-pro"},
        },
        "dominant_model_30d": "deepseek-v4-pro",
        "dominant_model_lane_30d": "default",
        "classification": {"tier": case["expected"]["profile_tier"], "reasons": [], "needs_followup": False},
        "windows": windows,
        "snapshot_evidence": None,
    }


def run_routing_cases(model_router, policy: dict, examples: dict, failures: list[str]) -> None:
    now_ts = datetime.now(timezone.utc).timestamp()
    original_build_profile_usage = model_router.build_profile_usage
    original_build_fleet_usage = model_router.build_fleet_usage
    original_load_benchmark = model_router.load_benchmark
    original_get_benchmark_scores = model_router.get_benchmark_scores
    original_load_overrides = model_router.load_overrides
    try:
        model_router.load_benchmark = lambda: None
        model_router.get_benchmark_scores = lambda benchmark: {}

        light_case = next(c for c in examples["routing_cases"] if c["name"] == "light_profile_inside_heavy_fleet")
        light_windows = merged_windows(model_router, next(c for c in examples["classification_cases"] if c["name"] == "light_profile")["windows"])
        heavy_windows = merged_windows(model_router, next(c for c in examples["classification_cases"] if c["name"] == "heavy_profile")["windows"])
        model_router.build_profile_usage = lambda profile, policy_obj, ts, snapshots=None: {
            "profile": profile,
            "current_main_provider": "nvidia",
            "current_main_model": "deepseek-v4-flash",
            "current_main_lane": "cheap",
            "current_vision_provider": "nvidia",
            "current_vision_model": "minimax-m3",
            "current_auxiliary_slots": {
                "vision": {"provider": "nvidia", "model": "minimax-m3"},
                "web_extract": {"provider": "nvidia", "model": "minimax-m3"},
            },
            "dominant_model_30d": "deepseek-v4-flash",
            "dominant_model_lane_30d": "cheap",
            "classification": {"tier": light_case["expected"]["profile_tier"], "reasons": [], "needs_followup": False},
            "windows": light_windows,
            "snapshot_evidence": None,
        }
        model_router.build_fleet_usage = lambda policy_obj, ts, snapshots=None: {
            "classification": {"tier": light_case["expected"]["fleet_tier"], "reasons": [], "needs_followup": False},
            "windows": heavy_windows,
            "snapshot_evidence": None,
        }
        model_router.load_overrides = lambda policy_obj: []
        _, routed = model_router.select_model("quick", "cost", profile="example-light-profile", allow_conservative_fallback=True)
        assert_equal("light_profile_inside_heavy_fleet profile_tier", routed["profile_tier"], light_case["expected"]["profile_tier"], failures)
        assert_equal("light_profile_inside_heavy_fleet fleet_tier", routed["fleet_tier"], light_case["expected"]["fleet_tier"], failures)
        assert_equal("light_profile_inside_heavy_fleet governing_tier", routed["governing_tier"], light_case["expected"]["governing_tier"], failures)
        assert_equal("light_profile_inside_heavy_fleet nvidia_eligible", routed["nvidia_eligible"], light_case["expected"]["nvidia_eligible"], failures)
        assert_true(
            "light_profile_inside_heavy_fleet migration",
            any("web_extract=nvidia/minimax-m3" in s for s in routed["migration_suggestions"]),
            failures,
            "expected migration suggestions to include non-vision NVIDIA aux slots",
        )

        for route_name, class_name in (("moderate_profile_route", "moderate_profile"), ("heavy_profile_route", "heavy_profile"), ("corp_profile_route", "corp_fleet")):
            route_case = next(c for c in examples["routing_cases"] if c["name"] == route_name)
            windows = merged_windows(model_router, next(c for c in examples["classification_cases"] if c["name"] == class_name)["windows"])
            model_router.build_profile_usage = lambda profile, policy_obj, ts, snapshots=None, rc=route_case, w=windows: make_stub_profile(rc, w)
            model_router.build_fleet_usage = lambda policy_obj, ts, snapshots=None, rc=route_case, w=windows: {
                "classification": {"tier": rc["expected"]["fleet_tier"], "reasons": [], "needs_followup": False},
                "windows": w,
                "snapshot_evidence": None,
            }
            _, routed = model_router.select_model("quick", "cost", profile="sirvir", allow_conservative_fallback=True)
            assert_equal(f"{route_name} profile_tier", routed["profile_tier"], route_case["expected"]["profile_tier"], failures)
            assert_equal(f"{route_name} fleet_tier", routed["fleet_tier"], route_case["expected"]["fleet_tier"], failures)
            assert_equal(f"{route_name} governing_tier", routed["governing_tier"], route_case["expected"]["governing_tier"], failures)
            assert_equal(f"{route_name} nvidia_eligible", routed["nvidia_eligible"], route_case["expected"]["nvidia_eligible"], failures)
            assert_equal(f"{route_name} best provider", routed["recommendation_lanes"]["best"]["provider"], route_case["expected"]["best_provider"], failures)
            assert_equal(f"{route_name} safest provider", routed["recommendation_lanes"]["safest"]["provider"], route_case["expected"]["safest_provider"], failures)

        expired_case = next(c for c in examples["routing_cases"] if c["name"] == "expired_override")
        model_router.load_overrides = lambda policy_obj: [{
            "scope": "profile",
            "target": "sirvir",
            "reason": "temporary test",
            "start_at": now_ts - 3600,
            "expires_at": now_ts - 60,
            "baseline_tier": "heavy",
            "override_tier": "light",
        }]
        override = model_router.resolve_override("sirvir", policy, now_ts)
        assert_equal("expired_override active", bool(override), expired_case["expected"]["override_active"], failures)
        assert_equal("expired_override baseline_restored", override is None, expired_case["expected"]["baseline_restored"], failures)

        active_case = next(c for c in examples["routing_cases"] if c["name"] == "active_override")
        model_router.load_overrides = lambda policy_obj: [{
            "scope": "profile",
            "target": "sirvir",
            "reason": "temporary test",
            "start_at": now_ts - 3600,
            "expires_at": now_ts + 3600,
            "baseline_tier": "heavy",
            "override_tier": "light",
        }]
        model_router.build_profile_usage = lambda profile, policy_obj, ts, snapshots=None: make_stub_profile(
            {"name": "active_override", "expected": {"profile_tier": "heavy"}},
            heavy_windows,
        )
        model_router.build_fleet_usage = lambda policy_obj, ts, snapshots=None: {
            "classification": {"tier": "heavy", "reasons": [], "needs_followup": False},
            "windows": heavy_windows,
            "snapshot_evidence": None,
        }
        _, overridden = model_router.select_model("quick", "cost", profile="sirvir", allow_conservative_fallback=True)
        assert_equal("active_override active", overridden["override_active"], active_case["expected"]["override_active"], failures)
        assert_equal("active_override governing_tier", overridden["governing_tier"], active_case["expected"]["governing_tier"], failures)
    finally:
        model_router.build_profile_usage = original_build_profile_usage
        model_router.build_fleet_usage = original_build_fleet_usage
        model_router.load_benchmark = original_load_benchmark
        model_router.get_benchmark_scores = original_get_benchmark_scores
        model_router.load_overrides = original_load_overrides


def run_audit_profile_filter_check(audit_fleet, failures: list[str]) -> None:
    policy = audit_fleet.load_policy()
    reports = [
        {
            "profile": "alpha",
            "windows": merged_windows(audit_fleet, {
                "30d": {"sessions": 10, "total_tokens": 1000000, "monthly_equivalent_tokens": 1000000, "monthly_equivalent_sessions": 10, "avg_tokens_per_session": 100000},
                "7d": {"sessions": 3, "total_tokens": 250000, "monthly_equivalent_tokens": 1071428.57, "monthly_equivalent_sessions": 12.86, "avg_tokens_per_session": 83333.33},
                "24h": {"sessions": 1, "total_tokens": 50000, "monthly_equivalent_tokens": 1500000, "monthly_equivalent_sessions": 30, "avg_tokens_per_session": 50000},
            }),
        },
        {
            "profile": "beta",
            "windows": merged_windows(audit_fleet, {
                "30d": {"sessions": 600, "total_tokens": 120000000, "monthly_equivalent_tokens": 120000000, "monthly_equivalent_sessions": 600, "avg_tokens_per_session": 200000},
                "7d": {"sessions": 150, "total_tokens": 28000000, "monthly_equivalent_tokens": 120000000, "monthly_equivalent_sessions": 642.86, "avg_tokens_per_session": 186666.67},
                "24h": {"sessions": 22, "total_tokens": 4500000, "monthly_equivalent_tokens": 135000000, "monthly_equivalent_sessions": 660, "avg_tokens_per_session": 204545.45},
            }),
        },
    ]
    fleet_all = audit_fleet.build_fleet_report(reports, policy)
    fleet_filtered = audit_fleet.build_fleet_report([reports[0]], policy)
    if fleet_all["classification"]["tier"] == fleet_filtered["classification"]["tier"]:
        failures.append("audit profile filter check did not produce a distinguishable fleet result")


def run_parser_checks(model_router, audit_fleet, failures: list[str]) -> None:
    router_cfg = model_router.load_yaml(ROOT_CONFIG_PATH)
    audit_cfg = audit_fleet.load_yaml(ROOT_CONFIG_PATH)
    for name, cfg in (("router", router_cfg), ("audit", audit_cfg)):
        assert_true(
            f"{name} fallback_providers list",
            isinstance(cfg.get("fallback_providers"), list) and cfg["fallback_providers"] and cfg["fallback_providers"][0].get("provider") == "openai-codex",
            failures,
            f"expected parsed fallback_providers list, got {cfg.get('fallback_providers')!r}",
        )
        assert_true(
            f"{name} toolsets list",
            cfg.get("toolsets") == ["hermes-cli"],
            failures,
            f"expected toolsets ['hermes-cli'], got {cfg.get('toolsets')!r}",
        )


def run_lane_classification_checks(model_router, audit_fleet, failures: list[str]) -> None:
    assert_equal("router deepseek-v4-flash lane", model_router.classify_deployed_lane("deepseek-v4-flash"), "cheap", failures)
    assert_equal("audit deepseek-v4-flash lane", audit_fleet.classify_deployed_lane("deepseek-v4-flash"), "cheap", failures)
    assert_equal("router deepseek-v4-pro lane", model_router.classify_deployed_lane("deepseek-v4-pro"), "default", failures)
    assert_equal("audit minimax lane", audit_fleet.classify_deployed_lane("minimaxai/minimax-m3"), "cheap", failures)


def run_followup_gating_check(failures: list[str]) -> None:
    blocked = invoke_python_json(
        [sys.executable, str(MODEL_ROUTER_PATH), "--task", "quick", "--priority", "cost", "--profile", "example-light-profile", "--json"],
        expect_exit=1,
    )
    assert_equal("followup gating required", blocked.get("followup_required"), True, failures)
    assert_true(
        "followup gating question present",
        bool(blocked.get("followup_question")),
        failures,
        f"expected followup question, got {blocked.get('followup_question')!r}",
    )
    assert_true(
        "followup gating hides provisional recommendation",
        "provisional_recommendation" not in blocked,
        failures,
        f"blocked response leaked provisional recommendation: {blocked.get('provisional_recommendation')!r}",
    )
    assert_true(
        "followup gating hides recommendation lanes",
        "recommendation_lanes" not in blocked,
        failures,
        f"blocked response leaked recommendation lanes: {blocked.get('recommendation_lanes')!r}",
    )
    allowed = invoke_python_json(
        [sys.executable, str(MODEL_ROUTER_PATH), "--task", "quick", "--priority", "cost", "--profile", "example-light-profile", "--allow-conservative-fallback", "--json"],
        expect_exit=0,
    )
    assert_equal("followup fallback success", allowed.get("followup_required"), False, failures)
    assert_true(
        "followup fallback lane exists",
        bool((allowed.get("recommendation_lanes") or {}).get("best")),
        failures,
        "expected best recommendation lane after conservative fallback",
    )


def run_snapshot_check(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="usage-tier-snapshot-") as tmp:
        tmpdir = Path(tmp)
        policy = json.loads(POLICY_PATH.read_text())
        snapshots_path = tmpdir / "snapshots.json"
        snapshots_path.write_text(json.dumps({
            "profiles": {"example-light-profile": {"minimum_tier": "moderate", "reason": "dashboard shows sustained provider saturation"}},
            "fleet": {}
        }))
        policy["provider_snapshots"] = {"state_path": str(snapshots_path)}
        policy_path = tmpdir / "policy.json"
        policy_path.write_text(json.dumps(policy))
        env = {**os.environ, "SIRVIR_USAGE_TIER_POLICY_PATH": str(policy_path)}
        routed = invoke_python_json(
            [sys.executable, str(MODEL_ROUTER_PATH), "--task", "quick", "--priority", "cost", "--profile", "example-light-profile", "--allow-conservative-fallback", "--json"],
            env=env,
            expect_exit=0,
        )
        assert_equal("snapshot escalated example-light-profile tier", routed.get("profile_tier"), "moderate", failures)
        assert_true(
            "snapshot evidence surfaced",
            (routed.get("snapshot_evidence") or {}).get("profile", {}).get("minimum_tier") == "moderate",
            failures,
            f"expected snapshot evidence in router output, got {routed.get('snapshot_evidence')!r}",
        )


def run_persisted_override_lifecycle_check(failures: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="usage-tier-override-") as tmp:
        tmpdir = Path(tmp)
        policy = json.loads(POLICY_PATH.read_text())
        overrides_path = tmpdir / "overrides.json"
        snapshots_path = tmpdir / "snapshots.json"
        snapshots_path.write_text(json.dumps({"profiles": {}, "fleet": {}}))
        policy["overrides"]["state_path"] = str(overrides_path)
        policy["provider_snapshots"] = {"state_path": str(snapshots_path)}
        policy_path = tmpdir / "policy.json"
        policy_path.write_text(json.dumps(policy))

        now_ts = datetime.now(timezone.utc).timestamp()
        overrides_path.write_text(json.dumps({
            "overrides": [{
                "scope": "profile",
                "target": "sirvir",
                "reason": "temporary test",
                "start_at": now_ts - 60,
                "expires_at": now_ts + 3600,
                "baseline_tier": "corp",
                "override_tier": "light"
            }]
        }))
        env_active = {
            **os.environ,
            "SIRVIR_USAGE_TIER_POLICY_PATH": str(policy_path),
            "SIRVIR_USAGE_TIER_NOW_TS": str(now_ts),
        }
        active = invoke_python_json(
            [sys.executable, str(MODEL_ROUTER_PATH), "--task", "quick", "--priority", "cost", "--profile", "sirvir", "--allow-conservative-fallback", "--json"],
            env=env_active,
            expect_exit=0,
        )
        assert_equal("persisted override active", active.get("override_active"), True, failures)
        assert_equal("persisted override governing", active.get("governing_tier"), "light", failures)

        env_expired = {
            **os.environ,
            "SIRVIR_USAGE_TIER_POLICY_PATH": str(policy_path),
            "SIRVIR_USAGE_TIER_NOW_TS": str(now_ts + 7200),
        }
        expired = invoke_python_json(
            [sys.executable, str(MODEL_ROUTER_PATH), "--task", "quick", "--priority", "cost", "--profile", "sirvir", "--allow-conservative-fallback", "--json"],
            env=env_expired,
            expect_exit=0,
        )
        assert_equal("persisted override expired", expired.get("override_active"), False, failures)
        assert_true(
            "persisted override baseline restored",
            expired.get("governing_tier") != "light",
            failures,
            f"expected baseline tier restored after expiry, got {expired.get('governing_tier')!r}",
        )


def main() -> int:
    model_router = load_module("sirvir_model_router", MODEL_ROUTER_PATH)
    audit_fleet = load_module("sirvir_audit_fleet", AUDIT_FLEET_PATH)
    policy = json.loads(POLICY_PATH.read_text())
    examples = json.loads(EXAMPLES_PATH.read_text())
    failures: list[str] = []

    run_classification_cases(model_router, policy, examples, failures)
    run_routing_cases(model_router, policy, examples, failures)
    run_audit_profile_filter_check(audit_fleet, failures)
    run_parser_checks(model_router, audit_fleet, failures)
    run_lane_classification_checks(model_router, audit_fleet, failures)
    run_followup_gating_check(failures)
    run_snapshot_check(failures)
    run_persisted_override_lifecycle_check(failures)

    result = {
        "status": "ok" if not failures else "failed",
        "checks_run": len(examples["classification_cases"]) + len(examples["routing_cases"]) + 10,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
