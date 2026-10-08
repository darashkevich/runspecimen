"""Pin QA docfix wording: verify vs signatures, README CLI parse, Codex listing."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path

from tests.helpers import SRC, ROOT

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.cli import build_parser


CLI_PATH = ROOT / "src" / "runspecimen" / "cli.py"
USER_GUIDE = ROOT / "docs" / "USER_GUIDE.md"
README = ROOT / "README.md"
HUMAN_ACCEPTANCE = ROOT / "docs" / "HUMAN-ACCEPTANCE.md"
PLUGIN_README = ROOT / "plugins" / "runspecimen" / "README.md"
VERIFY_INSTALLED = ROOT / "scripts" / "verify_installed_wheel.py"
PIN_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-08-qafix4"
QAFIX3_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-07-qafix3"
QAFIX_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-07-qafix2"
BUMP_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-06-bump"
WHEEL_NAME = "runspecimen-0.2.0rc15-py3-none-any.whl"
N3_GATING_NEEDLE = '"$RS" --version &&'

DIGEST_HELP_NEEDLE = (
    "verify checks receipt integrity, the event chain, and live "
    "provenance; it does not check HMAC or Ed25519 signatures. "
    "verify-signature does that, with its required trust inputs."
)
GUIDE_NEEDLE = (
    "`verify` checks receipt integrity, the event chain, and live provenance; it "
    "does not check HMAC or Ed25519 signatures. `verify-signature` does that"
)
FORBIDDEN_VERIFY_CLAIMS = (
    "Neither checks the event chain or signatures; `verify` does that.",
    "This does not check the event chain, signatures, or current provenance. Use verify for that.",
    "Use verify for that.",
)
CODEX_LISTING_CLAIMS = (
    "from the Codex plugin listing",
    "the Codex plugin listing",
)


def _digest_parser() -> argparse.ArgumentParser:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices["digest"]
    raise AssertionError("digest subparser missing")


def _bash_commands(markdown: str) -> list[str]:
    blocks = re.findall(r"```(?:bash|sh)?\n(.*?)```", markdown, flags=re.S)
    commands: list[str] = []
    for block in blocks:
        current = ""
        for raw in block.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if raw.rstrip().endswith("\\"):
                current += stripped[:-1].rstrip() + " "
                continue
            current += stripped
            commands.append(current)
            current = ""
        if current.strip():
            commands.append(current.strip())
    return commands


class Rc15QaDocfixTests(unittest.TestCase):
    def test_digest_help_does_not_claim_verify_checks_signatures(self) -> None:
        description = _digest_parser().description or ""
        self.assertIn(DIGEST_HELP_NEEDLE, description)
        self.assertNotIn("Use verify for that.", description)
        cli_text = CLI_PATH.read_text(encoding="utf-8")
        self.assertIn("it does not check HMAC or Ed25519 signatures.", cli_text)
        self.assertIn("verify-signature does that, with its required trust inputs.", cli_text)
        for needle in FORBIDDEN_VERIFY_CLAIMS:
            self.assertNotIn(needle, cli_text)

    def test_user_guide_pins_verify_versus_verify_signature(self) -> None:
        guide = USER_GUIDE.read_text(encoding="utf-8")
        collapsed = re.sub(r"\s+", " ", guide)
        self.assertIn(GUIDE_NEEDLE, collapsed)
        for needle in FORBIDDEN_VERIFY_CLAIMS:
            self.assertNotIn(needle, guide)
        self.assertNotIn("from the Codex plugin listing", guide)
        self.assertIn("not submitted and not listed", collapsed)
        self.assertIn("There is no public Codex plugin listing", collapsed)

    def test_readme_sign_and_hmac_verify_signature_examples_parse(self) -> None:
        parser = build_parser()
        found_sign = False
        found_verify = False
        for command in _bash_commands(README.read_text(encoding="utf-8")):
            if not command.startswith("runspecimen "):
                continue
            argv = shlex.split(command)[1:]
            if not argv:
                continue
            if argv[0] == "sign":
                args = parser.parse_args(argv)
                self.assertEqual(args.command, "sign")
                self.assertIsNotNone(args.contract)
                found_sign = True
            elif argv[0] == "verify-signature":
                args = parser.parse_args(argv)
                self.assertEqual(args.command, "verify-signature")
                self.assertIsNotNone(args.contract)
                found_verify = True
        self.assertTrue(found_sign, "README is missing a sign example")
        self.assertTrue(found_verify, "README is missing a verify-signature example")

    def test_plugin_readme_does_not_promise_a_codex_listing(self) -> None:
        text = PLUGIN_README.read_text(encoding="utf-8")
        for needle in CODEX_LISTING_CLAIMS:
            self.assertNotIn(needle, text)
        self.assertIn("not submitted and not listed", text)

    def test_human_acceptance_sheet_pins_venv_and_n10(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        self.assertIn("$VENV/bin/runspecimen", text)
        self.assertIn("command -v runspecimen", text)
        self.assertIn("mktemp -d", text)
        self.assertIn('test ! -e "$VENV"', text)
        self.assertIn("0.2.0rc15-2026-10-08-qafix4", text)
        self.assertIn("--no-index --no-deps --force-reinstall", text)
        self.assertIn("scripts/verify_installed_wheel.py", text)
        self.assertIn("--launcher", text)
        self.assertIn("wheel_sha256", text)
        self.assertIn("direct_url.json", text)
        self.assertIn("env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP", text)
        self.assertIn("PYTHONNOUSERSITE=1", text)
        self.assertIn("set -euo pipefail", text)
        self.assertIn(N3_GATING_NEEDLE, text)
        self.assertIn("realpath-equal to the verified package directory", text)
        self.assertIn("same absolute launcher and sanitized environment", text)
        self.assertIn("demo-campaign", text)
        self.assertIn("run-001", text)
        self.assertNotRegex(
            text,
            r'(?m)^(?:\$PY|"\$PY"|python3).*(?:pip install --upgrade|pip install -U)',
        )
        for command in _bash_commands(text):
            self.assertNotIn("pip install --upgrade", command)
            self.assertNotIn("pip install -U", command)
            if "verify_installed_wheel.py" in command:
                self.assertIn("&&", command)
                self.assertIn('"$RS" --version', command)
                self.assertNotRegex(command, r'"\$RS" --version\s*;')
        self.assertIn("execution policy local has no typed-phrase fallback", text)
        self.assertIn("## N10 — protected-policy refusal", text)
        self.assertIn("## Schema-rejection check (not N10)", text)
        self.assertIn("not_a_real_contract_field", text)
        self.assertIn("Homebrew", text)
        command_lines = [
            line.strip()
            for line in text.splitlines()
            if line.startswith("$VENV/")
            or line.startswith('"$RS"')
            or line.startswith('"$PY"')
            or line.startswith("$RS_SANITIZE")
            or line.startswith("set -euo")
            or line.startswith("env -u")
            or line.startswith("test ")
        ]
        for line in command_lines:
            self.assertNotIn(" #", line, f"trailing comment on command line: {line}")
            self.assertNotRegex(line, r"(^|\s)runspecimen\s", "bare runspecimen on a command line")
            self.assertNotRegex(line, r"(^|\s)python3\s")

    def test_human_acceptance_n3_fails_when_launcher_is_missing(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        gating = [
            command
            for command in _bash_commands(text)
            if "verify_installed_wheel.py" in command and '"$RS" --version' in command
        ]
        self.assertEqual(len(gating), 1, "N3 must have one launcher-then-verifier command")
        command = gating[0]
        self.assertIn("&&", command)
        self.assertIn("set -euo pipefail", command)
        pin = _pin_wheel()
        with tempfile.TemporaryDirectory(prefix="rs-ha-n3-missing-") as root:
            missing = Path(root) / "missing-runspecimen"
            env = os.environ.copy()
            env["RS"] = str(missing)
            env["PY"] = sys.executable
            env["WHEEL"] = str(pin.resolve()) if pin.is_file() else str(Path(root) / "no.whl")
            env["RS_SANITIZE"] = (
                "env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1"
            )
            env["PWD"] = str(ROOT)
            result = subprocess.run(
                ["bash", "-c", command],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(ROOT),
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_wheel_provenance_rejects_same_version_older_rc15(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        self.assertNotEqual(pin.read_bytes(), older.read_bytes())
        mismatch = _install_and_verify(older, pin)
        self.assertNotEqual(mismatch.returncode, 0, mismatch.stdout + mismatch.stderr)
        self.assertIn("does not match the pinned wheel", mismatch.stdout)
        match = _install_and_verify(pin, pin)
        self.assertEqual(match.returncode, 0, match.stdout + match.stderr)
        payload = json.loads(match.stdout.split("---")[0])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["origins_bound"])
        self.assertEqual(payload["import_overrides"], [])
        self.assertEqual(payload["pth_findings"], [])
        self.assertGreater(payload["checked"], 0)
        verified = Path(payload["verified_package_dir"]).resolve()
        self.assertEqual(Path(payload["runspecimen_file"]).resolve().parent, verified)
        self.assertEqual(Path(payload["cli_file"]).resolve().parent, verified)
        self.assertIn("direct_url.json", match.stdout)
        self.assertIn("RECORD", match.stdout)

    def test_installed_wheel_provenance_rejects_pythonpath_override(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        hijack = _install_and_verify(
            pin,
            pin,
            plant_older=older,
            extra_env_factory=_pythonpath_to_planted,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(
            any(item.startswith("PYTHONPATH=") for item in payload["import_overrides"]),
            payload["import_overrides"],
        )

    def test_installed_wheel_provenance_rejects_pth_prepend(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        hijack = _install_and_verify(pin, pin, plant_older=older, write_pth=True)
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["origins_bound"])
        self.assertTrue(payload["pth_findings"], payload)
        self.assertTrue(
            any("outside the verified install" in item.get("reason", "") for item in payload["pth_findings"]),
            payload["pth_findings"],
        )


def _pin_wheel() -> Path:
    for pack in (PIN_PACK, QAFIX3_PACK, QAFIX_PACK):
        pin = pack / WHEEL_NAME
        if pin.is_file():
            return pin
    return PIN_PACK / WHEEL_NAME


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_launcher(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "runspecimen.exe"
    return venv_dir / "bin" / "runspecimen"


def _sanitized_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONSTARTUP", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _plant_older_tree(py: Path, venv_dir: Path, older_wheel: Path, env: dict[str, str]) -> Path:
    target = venv_dir / "older"
    planted = subprocess.run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(target),
            str(older_wheel.resolve()),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if planted.returncode != 0:
        raise AssertionError(f"pip --target older failed: {planted.stderr}")
    return target.resolve()


def _pythonpath_to_planted(venv_dir: Path, planted: Path) -> dict[str, str]:
    env = _sanitized_env()
    env["PYTHONPATH"] = str(planted)
    return env


def _site_packages(py: Path, env: dict[str, str]) -> Path:
    result = subprocess.run(
        [str(py), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return Path(result.stdout.strip()).resolve()


def _install_and_verify(
    install_wheel: Path,
    pin_wheel: Path,
    *,
    plant_older: Path | None = None,
    write_pth: bool = False,
    extra_env_factory=None,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="rs-ha-prov-") as root:
        venv_dir = Path(root) / "venv"
        if venv_dir.exists():
            raise AssertionError(f"venv target already exists: {venv_dir}")
        venv.create(venv_dir, with_pip=True, symlinks=True)
        py = _venv_python(venv_dir)
        env = _sanitized_env()
        install = subprocess.run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(install_wheel.resolve()),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if install.returncode != 0:
            raise AssertionError(f"pip install failed: {install.stderr}")
        planted = None
        if plant_older is not None:
            planted = _plant_older_tree(py, venv_dir, plant_older, env)
            if write_pth:
                pth = _site_packages(py, env) / "zz_older_prepend.pth"
                pth.write_text(
                    f"import sys; sys.path.insert(0, {str(planted)!r})\n",
                    encoding="utf-8",
                )
        verify_env = extra_env_factory(venv_dir, planted) if extra_env_factory else env
        launcher = _venv_launcher(venv_dir)
        return subprocess.run(
            [
                str(py),
                str(VERIFY_INSTALLED),
                "--wheel",
                str(pin_wheel.resolve()),
                "--launcher",
                str(launcher),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=verify_env,
        )


if __name__ == "__main__":
    unittest.main()
