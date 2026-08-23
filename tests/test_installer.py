import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SIRVIR_GIT_URL = "https://github.com/SouthpawIN/sirvir.git"


class SirvirInstallerTests(unittest.TestCase):
    def test_install_source_is_full_git_url(self):
        text = (ROOT / "scripts" / "install").read_text()
        self.assertIn(f'SIRVIR_SOURCE="{SIRVIR_GIT_URL}"', text)
        self.assertNotIn('SIRVIR_SOURCE="SouthpawIN/sirvir"', text)
        self.assertNotIn("hermes profile install \"SouthpawIN/sirvir\"", text)

    def test_existing_sirvir_with_missing_turbofit_installs_plugin_then_updates_profile(self):
        commands, stdout = self._run_installer(sirvir_present=True, turbofit_present=False)
        self.assertLess(
            commands.index("plugins install --enable https://github.com/SouthpawIN/turbofit.git"),
            commands.index("profile update sirvir --yes"),
        )
        self.assertIn("profile show sirvir", commands)
        self.assertIn("Sirvir and Turbofit are installed", stdout)
        self.assertIn("hermes -p sirvir", stdout)
        self.assertIn("recommended models", stdout)

    def test_fresh_profile_install_uses_full_git_url(self):
        commands, stdout = self._run_installer(sirvir_present=False, turbofit_present=True)
        self.assertIn(f"profile install {SIRVIR_GIT_URL} --name sirvir --yes", commands)
        self.assertNotIn("profile install SouthpawIN/sirvir --name sirvir --yes", commands)
        self.assertIn("Sirvir and Turbofit are installed", stdout)

    def _run_installer(self, *, sirvir_present: bool, turbofit_present: bool):
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            log = tmp / "commands.log"
            fake = bin_dir / "hermes"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "set -eu\n"
                "printf '%s\\n' \"$*\" >> \"$FAKE_HERMES_LOG\"\n"
                "case \"$*\" in\n"
                "  'plugins list') [ -f \"$FAKE_TURBOFIT\" ] && echo 'turbofit enabled' || true ;;\n"
                "  'plugins install --enable https://github.com/SouthpawIN/turbofit.git') touch \"$FAKE_TURBOFIT\" ;;\n"
                "  'profile list') [ -f \"$FAKE_SIRVIR\" ] && echo 'sirvir' || true ;;\n"
                f"  'profile install {SIRVIR_GIT_URL} --name sirvir --yes') touch \"$FAKE_SIRVIR\" ;;\n"
                "  'profile update sirvir --yes') : ;;\n"
                "  'profile show sirvir') [ -f \"$FAKE_SIRVIR\" ] || exit 1 ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n"
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                "FAKE_HERMES_LOG": str(log),
                "FAKE_TURBOFIT": str(tmp / "turbofit-installed"),
                "FAKE_SIRVIR": str(tmp / "sirvir-installed"),
            }
            if sirvir_present:
                pathlib.Path(env["FAKE_SIRVIR"]).touch()
            if turbofit_present:
                pathlib.Path(env["FAKE_TURBOFIT"]).touch()

            result = subprocess.run(
                [str(ROOT / "scripts" / "install")],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            return log.read_text().splitlines(), result.stdout


if __name__ == "__main__":
    unittest.main()
