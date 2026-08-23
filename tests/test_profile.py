import pathlib
import struct
import unittest

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLOUD_MARKERS = {
    "anthropic",
    "deepseek",
    "gemini",
    "google",
    "groq",
    "mistral",
    "nvidia",
    "nous",
    "ollama-cloud",
    "openai-codex",
    "openrouter",
    "together",
    "xai",
}


class SirvirProfileTests(unittest.TestCase):
    def test_distribution_is_single_product(self):
        manifest = yaml.safe_load((ROOT / "distribution.yaml").read_text())
        self.assertEqual(manifest["name"], "sirvir")
        self.assertEqual(manifest["version"], "2.2.2")
        skill_text = (ROOT / "skills" / "sirvir" / "SKILL.md").read_text()
        skill_meta = yaml.safe_load(skill_text.split("---", 2)[1])
        self.assertEqual(skill_meta["version"], "2.2.2")
        self.assertEqual([d["name"] for d in manifest["dependencies"]], ["turbofit"])
        self.assertEqual(manifest["dependencies"][0]["repo"], "SouthpawIN/turbofit")
        self.assertEqual(manifest["distribution_owned"], [
            "README.md",
            "SOUL.md",
            "AGENTS.md",
            "config.yaml",
            "distribution.yaml",
            "assets/",
            "skills/sirvir/",
        ])

    def test_every_model_route_is_loopback_turbofit(self):
        config = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.assertEqual(config["_config_version"], 33)
        self.assertEqual(config["model"]["provider"], "custom:turbofit")
        self.assertEqual(config["model"]["default"], "auto")
        self.assertEqual(
            [item["provider"] for item in config["fallback_providers"]],
            ["nous", "nous", "nous", "nous", "nous"],
        )

        providers = config["providers"]
        self.assertEqual(list(providers), ["turbofit"])
        self.assertTrue(providers["turbofit"]["api"].startswith("http://127.0.0.1:8091/"))
        self.assertEqual(
            set(providers["turbofit"]["models"]),
            {"auto", "active:main", "active:aux"},
        )

        for role, route in config["auxiliary"].items():
            with self.subTest(role=role):
                self.assertEqual(route["provider"], "custom:turbofit")
                self.assertEqual(route["model"], "active:aux")

    def test_readme_artwork_is_committed_and_full_size(self):
        readme = (ROOT / "README.md").read_text()
        expected = {
            "assets/sirvir-hero.png": (1920, 1080),
            "assets/sirvir-support-loop.png": (1600, 900),
        }
        for relative, dimensions in expected.items():
            with self.subTest(relative=relative):
                path = ROOT / relative
                self.assertIn(relative, readme)
                self.assertTrue(path.is_file())
                data = path.read_bytes()[:24]
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", data[16:24]), dimensions)

    def test_no_cloud_provider_markers_in_active_profile(self):
        files = [
            ROOT / "SOUL.md",
            ROOT / "AGENTS.md",
            ROOT / "config.yaml",
            ROOT / "distribution.yaml",
            ROOT / "skills" / "sirvir" / "SKILL.md",
        ]
        text = "\n".join(path.read_text().lower() for path in files)
        found = sorted(marker for marker in CLOUD_MARKERS if marker in text)
        self.assertEqual(found, ["nous"], f"unexpected cloud provider markers remain: {found}")
        self.assertIn("bootstrap", text)

    def test_old_parallel_skills_are_removed(self):
        skill_manifests = sorted((ROOT / "skills").glob("**/SKILL.md"))
        self.assertEqual(skill_manifests, [ROOT / "skills" / "sirvir" / "SKILL.md"])

    def test_pr_authority_and_guardrails_are_explicit(self):
        text = "\n".join([
            (ROOT / "SOUL.md").read_text().lower(),
            (ROOT / "AGENTS.md").read_text().lower(),
            (ROOT / "skills" / "sirvir" / "SKILL.md").read_text().lower(),
        ])
        self.assertIn("standing authorization", text)
        self.assertIn("southpawin/turbofit", text)
        self.assertIn("gh pr create", text)
        self.assertIn("direct-push", text)
        self.assertIn("merge", text)
        self.assertIn("release", text)

    def test_turbofit_source_is_refreshed_from_github_before_product_answers(self):
        text = "\n".join([
            (ROOT / "README.md").read_text().lower(),
            (ROOT / "AGENTS.md").read_text().lower(),
            (ROOT / "skills" / "sirvir" / "SKILL.md").read_text().lower(),
        ])
        self.assertIn("https://github.com/southpawin/turbofit", text)
        self.assertIn("current default-branch commit", text)
        self.assertIn("record the commit sha", text)
        self.assertIn("never answer current product behavior from a bundled copy", text)

    def test_machine_comparison_contract_covers_physical_fit_and_evidence_states(self):
        text = "\n".join([
            (ROOT / "AGENTS.md").read_text().lower(),
            (ROOT / "skills" / "sirvir" / "SKILL.md").read_text().lower(),
        ])
        for required in (
            "operating system",
            "architecture",
            "system ram",
            "available storage",
            "accelerator vendor",
            "per-device memory",
            "topology",
            "measured",
            "portable-fit",
            "benchmark required",
            "unsupported",
            "blocked",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_turbofit_question_answer_mode_is_explicit(self):
        text = "\n".join([
            (ROOT / "README.md").read_text().lower(),
            (ROOT / "SOUL.md").read_text().lower(),
            (ROOT / "skills" / "sirvir" / "SKILL.md").read_text().lower(),
        ])
        self.assertIn("turbofit q&a", text)
        self.assertIn("cite the source path and commit", text)
        self.assertIn("answer first", text)

    def test_pr_workflow_requires_tests_release_gate_and_ci_readback(self):
        text = "\n".join([
            (ROOT / "AGENTS.md").read_text().lower(),
            (ROOT / "skills" / "sirvir" / "SKILL.md").read_text().lower(),
        ])
        self.assertIn("failing regression test", text)
        self.assertIn("scripts/release-check", text)
        self.assertIn("gh pr create", text)
        self.assertIn("read back", text)
        self.assertIn("ci", text)

    def test_bootstrap_order_is_explicit(self):
        text = "\n".join([
            (ROOT / "README.md").read_text().lower(),
            (ROOT / "SOUL.md").read_text().lower(),
            (ROOT / "AGENTS.md").read_text().lower(),
            (ROOT / "skills" / "sirvir" / "SKILL.md").read_text().lower(),
        ])
        self.assertIn("install, recommended-model download, and setup", text)
        self.assertIn("http://127.0.0.1:8091/v1/models", text)
        self.assertIn("bootstrap fallback", text)
        self.assertIn("https://github.com/southpawin/sirvir.git", text)
        self.assertNotIn("southpawin/sirvir\" --name sirvir", text)


if __name__ == "__main__":
    unittest.main()
