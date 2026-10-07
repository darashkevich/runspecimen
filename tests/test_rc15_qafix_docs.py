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
PIN_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-07-qafix2"
QAFIX_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-07-qafix"
BUMP_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-06-bump"
WHEEL_NAME = "runspecimen-0.2.0rc15-py3-none-any.whl"

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
        self.assertIn("0.2.0rc15-2026-10-07-qafix2", text)
        self.assertIn("--no-index --no-deps --force-reinstall", text)
        self.assertIn("scripts/verify_installed_wheel.py", text)
        self.assertIn("wheel_sha256", text)
        self.assertIn("direct_url.json", text)
        self.assertNotRegex(
            text,
            r'(?m)^(?:\$PY|"\$PY"|python3).*(?:pip install --upgrade|pip install -U)',
        )
        for command in _bash_commands(text):
            self.assertNotIn("pip install --upgrade", command)
            self.assertNotIn("pip install -U", command)
        self.assertIn("execution policy local has no typed-phrase fallback", text)
        self.assertIn("## N10 — protected-policy refusal", text)
        self.assertIn("## Schema-rejection check (not N10)", text)
        self.assertIn("not_a_real_contract_field", text)
        self.assertIn("Homebrew", text)
        command_lines = [
            line.strip()
            for line in text.splitlines()
            if line.startswith("$VENV/") or line.startswith('"$RS"') or line.startswith('"$PY"')
        ]
        for line in command_lines:
            self.assertNotIn(" #", line, f"trailing comment on command line: {line}")
            self.assertNotRegex(line, r"(^|\s)runspecimen\s", "bare runspecimen on a command line")
            self.assertNotRegex(line, r"(^|\s)python3\s")

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
        self.assertGreater(payload["checked"], 0)
        self.assertIn("direct_url.json", match.stdout)
        self.assertIn("RECORD", match.stdout)


def _pin_wheel() -> Path:
    pin = PIN_PACK / WHEEL_NAME
    if pin.is_file():
        return pin
    return QAFIX_PACK / WHEEL_NAME


def _install_and_verify(install_wheel: Path, pin_wheel: Path) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="rs-ha-prov-") as root:
        venv_dir = Path(root) / "venv"
        if venv_dir.exists():
            raise AssertionError(f"venv target already exists: {venv_dir}")
        venv.create(venv_dir, with_pip=True, symlinks=True)
        py = venv_dir / "bin" / "python"
        if os.name == "nt":
            py = venv_dir / "Scripts" / "python.exe"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONNOUSERSITE"] = "1"
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
        return subprocess.run(
            [str(py), str(VERIFY_INSTALLED), "--wheel", str(pin_wheel.resolve())],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )


if __name__ == "__main__":
    unittest.main()
