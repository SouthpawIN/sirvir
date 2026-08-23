import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SirvirInstallerTests(unittest.TestCase):
    def test_existing_sirvir_with_missing_turbofit_installs_plugin_then_updates_profile(self):
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
                "  'profile install SouthpawIN/sirvir --name sirvir --yes') touch \"$FAKE_SIRVIR\" ;;\n"
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
            pathlib.Path(env["FAKE_SIRVIR"]).touch()

            result = subprocess.run(
                [str(ROOT / "scripts" / "install")],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            commands = log.read_text().splitlines()
            self.assertLess(
                commands.index("plugins install --enable https://github.com/SouthpawIN/turbofit.git"),
                commands.index("profile update sirvir --yes"),
            )
            self.assertIn("profile show sirvir", commands)
            self.assertIn("Sirvir and Turbofit are installed", result.stdout)


if __name__ == "__main__":
    unittest.main()
