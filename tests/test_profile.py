import pathlib
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
        self.assertEqual([d["name"] for d in manifest["dependencies"]], ["turbofit"])
        self.assertEqual(manifest["dependencies"][0]["repo"], "SouthpawIN/turbofit")
        self.assertEqual(manifest["distribution_owned"], [
            "README.md",
            "SOUL.md",
            "AGENTS.md",
            "config.yaml",
            "distribution.yaml",
            "skills/sirvir/",
        ])

    def test_every_model_route_is_loopback_turbofit(self):
        config = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.assertEqual(config["_config_version"], 33)
        self.assertEqual(config["model"]["provider"], "custom:turbofit")
        self.assertEqual(config["model"]["default"], "auto")
        self.assertEqual(config["fallback_providers"], [])

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
        self.assertEqual(found, [], f"cloud provider markers remain: {found}")

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


if __name__ == "__main__":
    unittest.main()
