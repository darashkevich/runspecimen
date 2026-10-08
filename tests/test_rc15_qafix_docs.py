"""Pin QA docfix wording: verify vs signatures, README CLI parse, Codex listing."""

from __future__ import annotations

import argparse
import hashlib
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
CANDIDATE_MANIFEST = ROOT / "docs" / "CANDIDATE_MANIFEST.md"
PLUGIN_README = ROOT / "plugins" / "runspecimen" / "README.md"
VERIFY_INSTALLED = ROOT / "scripts" / "verify_installed_wheel.py"
PIN_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-08-qafix8"
QAFIX7_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-08-qafix7"
QAFIX6_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-08-qafix6"
QAFIX5_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-08-qafix5"
QAFIX4_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-08-qafix4"
QAFIX3_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-07-qafix3"
QAFIX_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-07-qafix2"
BUMP_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-06-bump"
WHEEL_NAME = "runspecimen-0.2.0rc15-py3-none-any.whl"
N3_VERSION_NEEDLE = "rs_ok N3-version"
N10_EXPECTED = "execution policy local has no typed-phrase fallback"
N10_ERROR_LINE = "RunSpecimen error: execution policy local has no typed-phrase fallback"
UNK_EXPECTED = "contract contains unknown field(s): not_a_real_contract_field"
UNK_ERROR_LINE = "RunSpecimen error: contract contains unknown field(s): not_a_real_contract_field"

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
        self.assertIn("0.2.0rc15-2026-10-08-qafix8", text)
        self.assertIn("--no-index --no-deps --force-reinstall", text)
        self.assertIn("scripts/verify_installed_wheel.py", text)
        self.assertIn("--launcher", text)
        self.assertIn("wheel_sha256", text)
        self.assertIn("direct_url.json", text)
        self.assertIn("env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP", text)
        self.assertIn("PYTHONNOUSERSITE=1", text)
        self.assertIn("rs() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 \"$RS\" \"$@\"; }", text)
        self.assertNotIn("set -euo pipefail", text)
        self.assertNotIn("set -e", text)
        self.assertNotIn("$RS_SANITIZE", text)
        self.assertIn(N3_VERSION_NEEDLE, text)
        self.assertIn("rs_ok N3-verify", text)
        self.assertIn("realpath-equal", text)
        self.assertIn("trusted interpreter", text)
        self.assertIn("only the Python interpreter and its stdlib", text)
        self.assertIn("_virtualenv*", text)
        self.assertIn("DistutilsMetaFinder", text)
        self.assertIn("distutils-precedence.pth", text)
        self.assertIn('"$PY" -m pip uninstall -y setuptools', text)
        self.assertIn("N1-setuptools", text)
        self.assertIn("stdlib `python3 -m venv`", text)
        self.assertIn("demo-campaign", text)
        self.assertIn("run-001", text)
        self.assertIn("HUMAN-ACCEPTANCE supplement qafix8", text)
        self.assertNotRegex(
            text,
            r'(?m)^(?:\$PY|"\$PY"|python3|py ).*(?:pip install --upgrade|pip install -U)',
        )
        for command in _bash_commands(text):
            self.assertNotIn("pip install --upgrade", command)
            self.assertNotIn("pip install -U", command)
        n3 = _fence_containing(text, "rs_ok N3-version")
        self.assertIn("rs --version", n3)
        self.assertIn("verify_installed_wheel.py", n3)
        self.assertIn("rs_ok N3-verify", n3)
        self.assertNotIn("&&", n3)
        self.assertIn(N10_EXPECTED, text)
        self.assertIn("## N10 — protected-policy refusal", text)
        self.assertIn("## Schema-rejection check (not N10)", text)
        self.assertIn("not_a_real_contract_field", text)
        self.assertIn("rs_neg N10", text)
        self.assertIn("rs_neg UNK", text)
        self.assertIn("rs_ok N8 $?", text)
        self.assertIn('grep -Fqx -- "$4"', text)
        self.assertIn(N10_ERROR_LINE, text)
        self.assertIn(UNK_ERROR_LINE, text)
        if CANDIDATE_MANIFEST.is_file():
            manifest = CANDIDATE_MANIFEST.read_text(encoding="utf-8")
            self.assertIn("| Candidate (this pass) |", manifest)
            self.assertIn("PR #63 head that records the qafix8 pack", manifest)
            self.assertIn("8015b6d8017e5566f7558cc916dc0ee470c653ad", manifest)
            self.assertIn("artifacts/0.2.0rc15-2026-10-08-qafix8/", manifest)
            self.assertIn("3b20ad6b179baab582ec97285dd7899f09f11574", manifest)
        self.assertIn("Homebrew", text)
        self.assertIn("STEP $1 exit=$2", text)
        command_lines = [
            line.strip()
            for line in text.splitlines()
            if line.startswith("$VENV/")
            or line.startswith('"$RS"')
            or line.startswith('"$PY"')
            or line.startswith("rs ")
            or line.startswith("py ")
            or line.startswith("rs_ok ")
            or line.startswith("rs_neg ")
            or line.startswith("test ")
            or line.startswith("python3 ")
        ]
        for line in command_lines:
            self.assertNotIn(" #", line, f"trailing comment on command line: {line}")
            self.assertNotRegex(line, r"(^|\s)runspecimen\s", "bare runspecimen on a command line")
            if "python3" in line:
                self.assertIn("python3 -m venv", line)

    def test_human_acceptance_n3_fails_when_launcher_is_missing(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        self._assert_n3_missing_launcher_stops("bash")

    def test_human_acceptance_n3_missing_launcher_stops_in_zsh(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        self._assert_n3_missing_launcher_stops(_require_zsh())

    def _assert_n3_missing_launcher_stops(self, shell: str) -> None:
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        helpers = _helper_functions(text)
        n3 = _fence_containing(text, "rs_ok N3-version")
        pin = _pin_wheel()
        with tempfile.TemporaryDirectory(prefix="rs-ha-n3-missing-") as root:
            missing = Path(root) / "missing-runspecimen"
            script = (
                f"export PACK={shlex.quote(str(PIN_PACK))}\n"
                f"export WHEEL={shlex.quote(str(pin.resolve()) if pin.is_file() else str(Path(root) / 'no.whl'))}\n"
                f"export RS={shlex.quote(str(missing))}\n"
                f"export PY={shlex.quote(sys.executable)}\n"
                f"{helpers}\n"
                f"{n3}\n"
                "echo REACHED_NEXT_STEP\n"
            )
            env = os.environ.copy()
            env["PWD"] = str(ROOT)
            result = subprocess.run(
                [shell, "-c", script],
                check=False,
                capture_output=True,
                text=True,
                env=env,
                cwd=str(ROOT),
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("STEP N3-version exit=", output)
            self.assertIn("FAIL:", output)
            self.assertNotIn("REACHED_NEXT_STEP", output)

    def test_human_acceptance_helpers_stop_in_bash_and_zsh(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        helpers = _helper_functions(HUMAN_ACCEPTANCE.read_text(encoding="utf-8"))
        script = helpers + "\nrs_ok demo 0\nrs_ok shouldfail 1\necho REACHED\n"
        shells = ["bash", _require_zsh()]
        for shell in shells:
            result = subprocess.run(
                [shell, "-c", script],
                check=False,
                capture_output=True,
                text=True,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("STEP demo exit=0", output)
            self.assertIn("FAIL: step shouldfail", output)
            self.assertNotIn("REACHED", output)

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

    def test_installed_wheel_provenance_rejects_env_shebang_with_old_python_on_path(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(
            pin,
            pin,
            plant_older=older,
            make_old_venv=True,
            after_install=_rewrite_launcher_env_shebang,
            extra_env_factory=_path_with_old_venv_first,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(
            result.stdout + result.stderr,
            r"unsupported shebang|env-based|/usr/bin/env",
        )

    def test_installed_wheel_provenance_accepts_absolute_shebang_with_old_python_on_path(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(
            pin,
            pin,
            plant_older=older,
            make_old_venv=True,
            extra_env_factory=_path_with_old_venv_first,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.split("---")[0])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["origins_bound"])

    def test_installed_wheel_provenance_rejects_absolute_shebang_to_old_interpreter(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(
            pin,
            pin,
            plant_older=older,
            make_old_venv=True,
            after_install=_rewrite_launcher_old_absolute_shebang,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("not this venv's own Python", result.stdout + result.stderr)

    def test_installed_wheel_provenance_rejects_sitecustomize_approve_preload(self) -> None:
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
            after_install=_write_sitecustomize_approve_preload,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(
            payload.get("startup_findings")
            or "sitecustomize" in str(payload.get("message", "")).lower()
            or (
                payload.get("loaded_runspecimen")
                and "approve" in str(payload.get("loaded_runspecimen"))
            ),
            payload,
        )

    def test_installed_wheel_provenance_rejects_sitecustomize_whole_package(self) -> None:
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
            after_install=_write_sitecustomize_whole_package,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])

    def test_installed_wheel_provenance_rejects_virtualenv_pth_qa_compat(self) -> None:
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
            after_install=_write_virtualenv_pth_qa_compat,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["pth_findings"], payload)

    def test_installed_wheel_provenance_rejects_standard_virtualenv_pth_body(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(pin, pin, after_install=_write_standard_virtualenv_pth)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["pth_findings"], payload)
        self.assertTrue(
            any("_virtualenv" in item.get("reason", "") or "_virtualenv" in item.get("text", "")
                for item in payload["pth_findings"]),
            payload["pth_findings"],
        )

    def test_installed_wheel_provenance_accepts_usercustomize_when_user_site_disabled(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(
            pin,
            pin,
            plant_older=older,
            after_install=_write_usercustomize_under_userbase,
            extra_env_factory=_env_with_userbase,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.split("---")[0])
        self.assertTrue(payload["ok"])

    def test_installed_wheel_provenance_accepts_inert_egg_link(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(
            pin,
            pin,
            plant_older=older,
            after_install=_write_inert_egg_link,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_wheel_provenance_rejects_egg_link_with_easy_install_pth(self) -> None:
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
            after_install=_write_egg_link_and_easy_install_pth,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["pth_findings"], payload)

    def test_installed_wheel_provenance_symlink_identical_bytes_accepted(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(pin, pin, after_install=_symlink_approve_identical_bytes)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_wheel_provenance_symlink_older_bytes_rejected(self) -> None:
        pin = _pin_wheel()
        older = BUMP_PACK / WHEEL_NAME
        if not pin.is_file() or not older.is_file():
            self.skipTest("pin and 2026-10-06-bump wheels must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(
            pin,
            pin,
            plant_older=older,
            after_install=_symlink_approve_older_bytes,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("does not match the pinned wheel", result.stdout)

    def test_verify_installed_wheel_rejects_missing_launcher(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        pin = _pin_wheel()
        wheel = str(pin.resolve()) if pin.is_file() else str(ROOT / "no.whl")
        result = subprocess.run(
            [
                sys.executable,
                str(VERIFY_INSTALLED),
                "--wheel",
                wheel,
                "--launcher",
                "/no/such/runspecimen",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=_sanitized_env(),
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("absolute launcher not found", result.stdout)

    def test_interpreter_from_launcher_rejects_env_shebang(self) -> None:
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-shebang-") as root:
            bindir = Path(root) / "bin"
            bindir.mkdir()
            python = bindir / "python"
            python.write_text("#!/bin/sh\n", encoding="utf-8")
            python.chmod(0o755)
            launcher = bindir / "runspecimen"
            launcher.write_text(
                "#!/usr/bin/env python3\nfrom runspecimen.cli import main\n",
                encoding="utf-8",
            )
            with self.assertRaises(module.UnsupportedShebangError) as ctx:
                module.interpreter_from_launcher(launcher)
            self.assertIn("unsupported shebang", str(ctx.exception))

    def test_interpreter_from_launcher_accepts_venv_absolute_shebang(self) -> None:
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-shebang-ok-") as root:
            bindir = Path(root) / "bin"
            bindir.mkdir()
            python = bindir / "python"
            python.write_text("#!/bin/sh\n", encoding="utf-8")
            python.chmod(0o755)
            launcher = bindir / "runspecimen"
            launcher.write_text(
                f"#!{python}\nfrom runspecimen.cli import main\n",
                encoding="utf-8",
            )
            got = module.interpreter_from_launcher(launcher)
            self.assertEqual(got, python)

    def test_human_acceptance_rs_neg_requires_complete_line(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        helpers = _helper_functions(HUMAN_ACCEPTANCE.read_text(encoding="utf-8"))
        substring = helpers + (
            f"\nrs_neg N10 1 'prefix {N10_EXPECTED} suffix' {shlex.quote(N10_ERROR_LINE)}\n"
            "echo REACHED\n"
        )
        complete = helpers + (
            f"\nrs_neg N10 1 {shlex.quote(N10_ERROR_LINE)} {shlex.quote(N10_ERROR_LINE)}\n"
            "echo REACHED\n"
        )
        for shell in ("bash", _require_zsh()):
            with self.subTest(shell=shell, kind="substring"):
                result = subprocess.run(
                    [shell, "-c", substring],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("complete line", output)
                self.assertNotIn("REACHED", output)
            with self.subTest(shell=shell, kind="complete"):
                result = subprocess.run(
                    [shell, "-c", complete],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("PASS: N10", output)
                self.assertIn("REACHED", output)

    def test_human_acceptance_sheet_n1_n7_n10_unk_in_bash(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        self._assert_acceptance_sheet("bash")

    def test_human_acceptance_sheet_n1_n7_n10_unk_in_zsh(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE is not packed into the sdist")
        self._assert_acceptance_sheet(_require_zsh())

    def _assert_acceptance_sheet(self, shell: str) -> None:
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="rs-ha-sheet-") as root:
            pack = Path(root) / "pack"
            _build_sheet_pack(pack)
            script = _acceptance_sheet_script(text, pack)
            result = subprocess.run(
                [shell, "-c", script],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(ROOT),
                env=_sanitized_env(),
                timeout=180,
            )
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            for step in (
                "N1-wheel",
                "N1-venv-absent",
                "N1-venv",
                "N1-setuptools",
                "N2-hash",
                "N2-install",
                "N3-version",
                "N3-verify",
                "N4",
                "N5",
                "N6",
                "N7",
                "N10-init",
                "N10-edit",
                "UNK-init",
                "UNK-edit",
            ):
                self.assertIn(f"STEP {step} exit=0", output)
            self.assertIn("PASS: N10", output)
            self.assertIn("PASS: UNK", output)
            self.assertNotIn("FAIL:", output)
            self.assertNotIn("STEP N8 ", output)
            self.assertNotIn("STEP N9-", output)

    def test_qa3_01_env_shebang_is_refused(self) -> None:
        self.test_interpreter_from_launcher_rejects_env_shebang()

    def test_qa3_02_sitecustomize_approve_preload_is_refused(self) -> None:
        self.test_installed_wheel_provenance_rejects_sitecustomize_approve_preload()

    def test_qa3_03_sheet_n3_failure_stops_later_steps(self) -> None:
        self.test_human_acceptance_n3_fails_when_launcher_is_missing()
        self.test_human_acceptance_n3_missing_launcher_stops_in_zsh()

    def test_qa3_control_matrix_named_outcomes(self) -> None:
        """QA #3 control matrix: shebang, origins, startup hooks, sheet stop."""
        self.test_qa3_01_env_shebang_is_refused()
        self.test_installed_wheel_provenance_accepts_absolute_shebang_with_old_python_on_path()
        self.test_qa3_02_sitecustomize_approve_preload_is_refused()
        self.test_installed_wheel_provenance_rejects_pth_prepend()
        self.test_human_acceptance_helpers_stop_in_bash_and_zsh()

    def test_qa4_lazy_import_after_verification_is_bound(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(pin, pin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.split("---")[0])
        self.assertTrue(payload["ok"])
        lazy = payload.get("lazy_loaded_runspecimen") or {}
        self.assertTrue(lazy, payload)
        verified = Path(payload["verified_package_dir"]).resolve()
        for name, origin in lazy.items():
            self.assertIsNotNone(origin, name)
            got = Path(str(origin)).resolve()
            self.assertTrue(
                verified == got.parent or verified in got.parents,
                (name, got, verified),
            )

    def test_qa4_meta_path_finder_via_startup_hook_is_rejected(self) -> None:
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
            after_install=_write_virtualenv_meta_path_hijack,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        findings = payload.get("meta_path_findings") or []
        message = str(payload.get("message", ""))
        self.assertTrue(
            findings
            or payload.get("pth_findings")
            or "unexpected sys.meta_path" in message
            or "acceptance sheet" in message,
            payload,
        )

    def test_qa4_distutils_metafinder_is_not_treated_as_a_hijack(self) -> None:
        """Changed in QA-HOOKS-03: leftover DistutilsMetaFinder is extra startup.

        The previous allowlist (real class identity + setuptools RECORD) is
        gone. A venv that still has setuptools' distutils-precedence.pth is
        refused. Clean acceptance is the sheet-prepared venv without setuptools.
        """
        text = VERIFY_INSTALLED.read_text(encoding="utf-8")
        self.assertIn("DistutilsMetaFinder", text)
        self.assertNotIn("KNOWN_SAFE_PTH_IMPORT_LINES", text)
        self.assertNotIn("setuptools_distutils_hack_findings", text)
        self.assertNotIn("type(finder) is not _real_dmf", text)
        self.assertNotIn("if rec['module'] not in allowed_meta", text)
        self.assertNotIn('"import _virtualenv"', text)
        self.test_qa_hooks_03_leftover_setuptools_pth_is_rejected()

    def test_qa_hooks_01_spoofed_distutils_metafinder_via_virtualenv_is_rejected(self) -> None:
        """Reviewer spoof: import _virtualenv + fake DistutilsMetaFinder + old signing.py."""
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
            after_install=_write_reviewer_distutils_metafinder_spoof,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload.get("pth_findings") or payload.get("meta_path_findings"), payload)

    def test_qa_hooks_01_fake_named_finder_via_sitecustomize_is_rejected(self) -> None:
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
            after_install=_write_sitecustomize_named_distutils_finder,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(
            payload.get("startup_findings")
            or payload.get("meta_path_findings")
            or "sitecustomize" in str(payload.get("message", "")).lower()
            or "unexpected sys.meta_path" in str(payload.get("message", "")),
            payload,
        )

    def test_qa_hooks_01_clean_stdlib_venv_with_real_setuptools_shim_is_accepted(self) -> None:
        """Changed in QA-HOOKS-03: leftover setuptools shim is no longer accepted.

        Clean sheet venv acceptance is test_qa_hooks_03_clean_sheet_venv_is_accepted.
        """
        self.test_qa_hooks_03_leftover_setuptools_pth_is_rejected()

    def test_qa_hooks_02_virtualenv_pth_and_module_are_rejected(self) -> None:
        self.test_installed_wheel_provenance_rejects_standard_virtualenv_pth_body()

    def test_qa_hooks_03_leftover_setuptools_pth_is_rejected(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(pin, pin, after_install=_write_leftover_setuptools_pth)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["pth_findings"], payload)
        message = str(payload.get("message", ""))
        self.assertIn("acceptance sheet", message)
        self.assertIn("extra startup code", message)
        self.assertTrue(
            any("distutils-precedence.pth" in item.get("path", "") for item in payload["pth_findings"]),
            payload["pth_findings"],
        )

    def test_qa_hooks_03_clean_sheet_venv_is_accepted(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        result = _install_and_verify(pin, pin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout.split("---")[0])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["origins_bound"])
        self.assertEqual(payload["pth_findings"], [])
        self.assertEqual(payload.get("meta_path_findings") or [], [])
        self.assertEqual(payload.get("path_hook_findings") or [], [])

    def test_qa_hooks_03_file_and_record_tamper_class_find_spec_is_rejected(self) -> None:
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
            after_install=_write_reviewer_file_record_tamper_class,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertIn("acceptance sheet", str(payload.get("message", "")))

    def test_qa_hooks_03_file_and_record_tamper_instance_find_spec_is_rejected(self) -> None:
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
            after_install=_write_reviewer_file_record_tamper_instance,
        )
        self.assertNotEqual(hijack.returncode, 0, hijack.stdout + hijack.stderr)
        payload = json.loads(hijack.stdout.split("---")[0])
        self.assertFalse(payload["ok"])
        self.assertIn("acceptance sheet", str(payload.get("message", "")))

    def test_known_safe_pth_does_not_trust_import_virtualenv(self) -> None:
        module = _load_verify_module()
        self.assertFalse(getattr(module, "KNOWN_SAFE_PTH_IMPORT_LINES", None))
        with tempfile.TemporaryDirectory(prefix="rs-venv-art-") as root:
            site = Path(root)
            (site / "_virtualenv.pth").write_text("import _virtualenv\n", encoding="utf-8")
            (site / "_virtualenv.py").write_text("# stub\n", encoding="utf-8")
            findings = module.scan_pth_files(site) + module.scan_virtualenv_artifacts(site)
            reasons = " ".join(item.get("reason", "") + " " + item.get("text", "") for item in findings)
            self.assertTrue(findings)
            self.assertIn("_virtualenv", reasons)


def _pin_wheel() -> Path:
    for pack in (PIN_PACK, QAFIX7_PACK, QAFIX6_PACK, QAFIX5_PACK, QAFIX4_PACK, QAFIX3_PACK, QAFIX_PACK):
        pin = pack / WHEEL_NAME
        if pin.is_file():
            return pin
    return PIN_PACK / WHEEL_NAME


def _zsh_path() -> str | None:
    from shutil import which

    return which("zsh")


def _require_zsh() -> str:
    zsh = _zsh_path()
    if zsh is None:
        raise AssertionError(
            "zsh must be installed on this job; a skip for missing zsh is not a pass"
        )
    return zsh


def _build_sheet_pack(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    env = _sanitized_env()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(dest),
            str(ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise AssertionError(f"pip wheel failed: {result.stdout}\n{result.stderr}")
    wheels = list(dest.glob("runspecimen-0.2.0rc15-*.whl"))
    if len(wheels) != 1:
        raise AssertionError(f"expected one freshly built wheel in {dest}, got {wheels}")
    wheel = wheels[0]
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (dest / "SHA256SUMS").write_text(f"{digest}  {wheel.name}\n", encoding="utf-8")
    return wheel


def _acceptance_sheet_script(markdown: str, pack: Path) -> str:
    blocks = re.findall(r"```(?:bash|sh)?\n(.*?)```", markdown, flags=re.S)
    parts: list[str] = []
    for block in blocks:
        if "rs_ok N8" in block or "rs_ok N9-" in block:
            continue
        if "Session: HUMAN-ACCEPTANCE" in block:
            continue
        parts.append(block.rstrip() + "\n")
    script = "".join(parts)
    replaced, count = re.subn(
        r'export PACK="\$PWD/artifacts/0\.2\.0rc15-2026-10-08-qafix8"',
        f"export PACK={shlex.quote(str(pack))}",
        script,
        count=1,
    )
    if count != 1:
        raise AssertionError("could not rewrite PACK export in HUMAN-ACCEPTANCE sheet")
    return replaced


def _fence_containing(markdown: str, needle: str) -> str:
    blocks = re.findall(r"```(?:bash|sh)?\n(.*?)```", markdown, flags=re.S)
    hits = [block for block in blocks if needle in block]
    if len(hits) != 1:
        raise AssertionError(f"expected one fence containing {needle!r}, got {len(hits)}")
    return hits[0]


def _helper_functions(markdown: str) -> str:
    block = _fence_containing(markdown, "rs() {")
    lines = [
        line
        for line in block.splitlines()
        if not line.strip().startswith("export ")
    ]
    return "\n".join(lines)


def _load_verify_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("verify_installed_wheel", VERIFY_INSTALLED)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _pythonpath_to_planted(venv_dir: Path, planted: Path, old_venv: Path | None = None) -> dict[str, str]:
    env = _sanitized_env()
    env["PYTHONPATH"] = str(planted)
    return env


def _path_with_old_venv_first(venv_dir: Path, planted: Path, old_venv: Path | None = None) -> dict[str, str]:
    env = _sanitized_env()
    if old_venv is None:
        raise AssertionError("old venv is required to prepend PATH")
    old_bin = old_venv / ("Scripts" if os.name == "nt" else "bin")
    env["PATH"] = str(old_bin) + os.pathsep + env.get("PATH", "")
    return env


def _env_with_userbase(venv_dir: Path, planted: Path, old_venv: Path | None = None) -> dict[str, str]:
    env = _sanitized_env()
    env["PYTHONUSERBASE"] = str(venv_dir / "userbase")
    env["PYTHONNOUSERSITE"] = "1"
    return env


class _ProvHook:
    def __init__(
        self,
        *,
        venv_dir: Path,
        py: Path,
        launcher: Path,
        site: Path,
        planted: Path | None,
        old_venv: Path | None,
        env: dict[str, str],
    ) -> None:
        self.venv_dir = venv_dir
        self.py = py
        self.launcher = launcher
        self.site = site
        self.planted = planted
        self.old_venv = old_venv
        self.env = env


def _rewrite_launcher_env_shebang(hook: _ProvHook) -> None:
    text = hook.launcher.read_text(encoding="utf-8")
    lines = text.splitlines(True)
    if not lines:
        raise AssertionError("empty launcher")
    lines[0] = "#!/usr/bin/env python3\n"
    hook.launcher.write_text("".join(lines), encoding="utf-8")


def _rewrite_launcher_old_absolute_shebang(hook: _ProvHook) -> None:
    if hook.old_venv is None:
        raise AssertionError("old venv is required for an old absolute shebang")
    old_py = _venv_python(hook.old_venv)
    text = hook.launcher.read_text(encoding="utf-8")
    lines = text.splitlines(True)
    lines[0] = f"#!{old_py}\n"
    hook.launcher.write_text("".join(lines), encoding="utf-8")


def _approve_preload_source(planted: Path) -> str:
    old_pkg = (planted / "runspecimen").resolve()
    return (
        "import sys\n"
        "import runspecimen\n"
        f"_old = {str(old_pkg)!r}\n"
        "_orig = list(runspecimen.__path__)\n"
        "runspecimen.__path__.insert(0, _old)\n"
        "sys.modules.pop('runspecimen.approve', None)\n"
        "import runspecimen.approve as _approve\n"
        "runspecimen.__path__[:] = _orig\n"
    )


def _write_sitecustomize_approve_preload(hook: _ProvHook) -> None:
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    (hook.site / "sitecustomize.py").write_text(_approve_preload_source(hook.planted), encoding="utf-8")


def _write_sitecustomize_whole_package(hook: _ProvHook) -> None:
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    (hook.site / "sitecustomize.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(hook.planted)!r})\n",
        encoding="utf-8",
    )


def _write_virtualenv_pth_qa_compat(hook: _ProvHook) -> None:
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    (hook.site / "qa_compat.py").write_text(_approve_preload_source(hook.planted), encoding="utf-8")
    (hook.site / "_virtualenv.pth").write_text("import qa_compat\n", encoding="utf-8")


def _write_standard_virtualenv_pth(hook: _ProvHook) -> None:
    (hook.site / "_virtualenv.py").write_text("# standard virtualenv bootstrap stub\n", encoding="utf-8")
    (hook.site / "_virtualenv.pth").write_text("import _virtualenv\n", encoding="utf-8")


def _write_reviewer_distutils_metafinder_spoof(hook: _ProvHook) -> None:
    """QA-HOOKS-01: ``import _virtualenv`` plus a fake DistutilsMetaFinder.

    The fake class claims ``__module__='_distutils_hack'``, execs an older
    ``signing.py``, and spoofs ``__file__`` to the hashed installed member.
    """
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    old_signing = str((hook.planted / "runspecimen" / "signing.py").resolve())
    hashed_signing = str((hook.site / "runspecimen" / "signing.py").resolve())
    (hook.site / "_virtualenv.py").write_text(
        "import sys\n"
        "from importlib.abc import Loader, MetaPathFinder\n"
        "from importlib.machinery import ModuleSpec\n"
        "from pathlib import Path\n"
        f"_OLD = {old_signing!r}\n"
        f"_HASHED = {hashed_signing!r}\n"
        "class DistutilsMetaFinder(MetaPathFinder):\n"
        "    def find_spec(self, fullname, path, target=None):\n"
        "        if fullname != 'runspecimen.signing':\n"
        "            return None\n"
        "        return ModuleSpec(fullname, _SpoofLoader(), origin=_HASHED)\n"
        "class _SpoofLoader(Loader):\n"
        "    def create_module(self, spec):\n"
        "        return None\n"
        "    def exec_module(self, module):\n"
        "        module.__file__ = _HASHED\n"
        "        code = Path(_OLD).read_text(encoding='utf-8')\n"
        "        exec(compile(code, _HASHED, 'exec'), module.__dict__)\n"
        "DistutilsMetaFinder.__module__ = '_distutils_hack'\n"
        "sys.meta_path.insert(0, DistutilsMetaFinder())\n",
        encoding="utf-8",
    )
    (hook.site / "_virtualenv.pth").write_text("import _virtualenv\n", encoding="utf-8")


def _write_sitecustomize_named_distutils_finder(hook: _ProvHook) -> None:
    """Fake DistutilsMetaFinder added by sitecustomize, claiming the real module name."""
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    old_signing = str((hook.planted / "runspecimen" / "signing.py").resolve())
    hashed_signing = str((hook.site / "runspecimen" / "signing.py").resolve())
    (hook.site / "sitecustomize.py").write_text(
        "import sys\n"
        "from importlib.abc import Loader, MetaPathFinder\n"
        "from importlib.machinery import ModuleSpec\n"
        "from pathlib import Path\n"
        f"_OLD = {old_signing!r}\n"
        f"_HASHED = {hashed_signing!r}\n"
        "class DistutilsMetaFinder(MetaPathFinder):\n"
        "    def find_spec(self, fullname, path, target=None):\n"
        "        if fullname != 'runspecimen.signing':\n"
        "            return None\n"
        "        return ModuleSpec(fullname, _SpoofLoader(), origin=_HASHED)\n"
        "class _SpoofLoader(Loader):\n"
        "    def create_module(self, spec):\n"
        "        return None\n"
        "    def exec_module(self, module):\n"
        "        module.__file__ = _HASHED\n"
        "        code = Path(_OLD).read_text(encoding='utf-8')\n"
        "        exec(compile(code, _HASHED, 'exec'), module.__dict__)\n"
        "DistutilsMetaFinder.__module__ = '_distutils_hack'\n"
        "sys.meta_path.insert(0, DistutilsMetaFinder())\n",
        encoding="utf-8",
    )


def _setuptools_pth_body() -> str:
    return (
        "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; "
        "enabled = os.environ.get(var, 'local') == 'local'; "
        "enabled and __import__('_distutils_hack').add_shim();\n"
    )


def _record_sha256_field(data: bytes) -> str:
    import base64

    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
    return f"sha256={digest}"


def _write_matching_setuptools_record(site: Path, members: dict[str, bytes]) -> None:
    dist_info = site / "setuptools-84.0.0.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, data in members.items():
        lines.append(f"{name},{_record_sha256_field(data)},{len(data)}")
    lines.append("setuptools-84.0.0.dist-info/RECORD,,")
    (dist_info / "RECORD").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hijack_distutils_hack_source(
    *,
    old_signing: str,
    hashed_signing: str,
    as_class: bool,
) -> str:
    insert = "DistutilsMetaFinder()" if not as_class else "DistutilsMetaFinder"
    return (
        "import sys\n"
        "from importlib.abc import Loader, MetaPathFinder\n"
        "from importlib.machinery import ModuleSpec\n"
        "from pathlib import Path\n"
        f"_OLD = {old_signing!r}\n"
        f"_HASHED = {hashed_signing!r}\n"
        "class DistutilsMetaFinder(MetaPathFinder):\n"
        "    def find_spec(self, fullname, path, target=None):\n"
        "        if fullname != 'runspecimen.signing':\n"
        "            return None\n"
        "        return ModuleSpec(fullname, _SpoofLoader(), origin=_HASHED)\n"
        "class _SpoofLoader(Loader):\n"
        "    def create_module(self, spec):\n"
        "        return None\n"
        "    def exec_module(self, module):\n"
        "        module.__file__ = _HASHED\n"
        "        code = Path(_OLD).read_text(encoding='utf-8')\n"
        "        exec(compile(code, _HASHED, 'exec'), module.__dict__)\n"
        "def add_shim():\n"
        f"    sys.meta_path.insert(0, {insert})\n"
        "add_shim()\n"
    )


def _write_leftover_setuptools_pth(hook: _ProvHook) -> None:
    """A venv that still has setuptools' distutils-precedence.pth."""
    pth = _setuptools_pth_body()
    shim = (
        "class DistutilsMetaFinder:\n"
        "    def find_spec(self, fullname, path, target=None):\n"
        "        return None\n"
        "def add_shim():\n"
        "    import sys\n"
        "    sys.meta_path.insert(0, DistutilsMetaFinder())\n"
    )
    hack_dir = hook.site / "_distutils_hack"
    hack_dir.mkdir(parents=True, exist_ok=True)
    init = hack_dir / "__init__.py"
    init.write_text(shim, encoding="utf-8")
    (hook.site / "distutils-precedence.pth").write_text(pth, encoding="utf-8")
    _write_matching_setuptools_record(
        hook.site,
        {
            "_distutils_hack/__init__.py": init.read_bytes(),
            "distutils-precedence.pth": pth.encode("utf-8"),
        },
    )


def _write_reviewer_file_record_tamper(hook: _ProvHook, *, as_class: bool) -> None:
    """QA-HOOKS-03: replace _distutils_hack and rewrite the matching RECORD line."""
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    old_signing = str((hook.planted / "runspecimen" / "signing.py").resolve())
    hashed_signing = str((hook.site / "runspecimen" / "signing.py").resolve())
    source = _hijack_distutils_hack_source(
        old_signing=old_signing,
        hashed_signing=hashed_signing,
        as_class=as_class,
    )
    hack_dir = hook.site / "_distutils_hack"
    hack_dir.mkdir(parents=True, exist_ok=True)
    init = hack_dir / "__init__.py"
    init.write_text(source, encoding="utf-8")
    pth = _setuptools_pth_body()
    (hook.site / "distutils-precedence.pth").write_text(pth, encoding="utf-8")
    _write_matching_setuptools_record(
        hook.site,
        {
            "_distutils_hack/__init__.py": init.read_bytes(),
            "distutils-precedence.pth": pth.encode("utf-8"),
        },
    )


def _write_reviewer_file_record_tamper_class(hook: _ProvHook) -> None:
    _write_reviewer_file_record_tamper(hook, as_class=True)


def _write_reviewer_file_record_tamper_instance(hook: _ProvHook) -> None:
    _write_reviewer_file_record_tamper(hook, as_class=False)


def _write_virtualenv_meta_path_hijack(hook: _ProvHook) -> None:
    """``import _virtualenv`` pth with a custom meta_path finder."""
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    old_signing = str((hook.planted / "runspecimen" / "signing.py").resolve())
    (hook.site / "_virtualenv.py").write_text(
        "import sys\n"
        "from importlib.abc import Loader, MetaPathFinder\n"
        "from importlib.machinery import ModuleSpec\n"
        "from pathlib import Path\n"
        f"_TARGET = {old_signing!r}\n"
        "class _HijackLoader(Loader):\n"
        "    def create_module(self, spec):\n"
        "        return None\n"
        "    def exec_module(self, module):\n"
        "        module.__file__ = _TARGET\n"
        "        code = Path(_TARGET).read_text(encoding='utf-8')\n"
        "        exec(compile(code, _TARGET, 'exec'), module.__dict__)\n"
        "class _HijackFinder(MetaPathFinder):\n"
        "    def find_spec(self, fullname, path, target=None):\n"
        "        if fullname != 'runspecimen.signing':\n"
        "            return None\n"
        "        return ModuleSpec(fullname, _HijackLoader(), origin=_TARGET)\n"
        "sys.meta_path.insert(0, _HijackFinder())\n",
        encoding="utf-8",
    )
    (hook.site / "_virtualenv.pth").write_text("import _virtualenv\n", encoding="utf-8")


def _write_usercustomize_under_userbase(hook: _ProvHook) -> None:
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    user_site = hook.venv_dir / "userbase" / "lib" / f"python{version}" / "site-packages"
    user_site.mkdir(parents=True, exist_ok=True)
    (user_site / "usercustomize.py").write_text(
        _approve_preload_source(hook.planted),
        encoding="utf-8",
    )


def _write_inert_egg_link(hook: _ProvHook) -> None:
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    (hook.site / "runspecimen.egg-link").write_text(str(hook.planted) + "\n", encoding="utf-8")


def _write_egg_link_and_easy_install_pth(hook: _ProvHook) -> None:
    _write_inert_egg_link(hook)
    (hook.site / "easy-install.pth").write_text(str(hook.planted) + "\n", encoding="utf-8")


def _symlink_approve_identical_bytes(hook: _ProvHook) -> None:
    approve = hook.site / "runspecimen" / "approve.py"
    backup = hook.site / "approve_identical.py"
    backup.write_bytes(approve.read_bytes())
    approve.unlink()
    approve.symlink_to(backup)


def _symlink_approve_older_bytes(hook: _ProvHook) -> None:
    if hook.planted is None:
        raise AssertionError("planted older tree is required")
    approve = hook.site / "runspecimen" / "approve.py"
    approve.unlink()
    approve.symlink_to(hook.planted / "runspecimen" / "approve.py")


def _site_packages(py: Path, env: dict[str, str]) -> Path:
    result = subprocess.run(
        [str(py), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return Path(result.stdout.strip()).resolve()


def _uninstall_setuptools(py: Path, env: dict[str, str]) -> None:
    result = subprocess.run(
        [str(py), "-m", "pip", "uninstall", "-y", "setuptools"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(f"pip uninstall setuptools failed: {result.stderr}")


def _create_venv_and_install(venv_dir: Path, wheel: Path, env: dict[str, str]) -> Path:
    if venv_dir.exists():
        raise AssertionError(f"venv target already exists: {venv_dir}")
    venv.create(venv_dir, with_pip=True, symlinks=True)
    py = _venv_python(venv_dir)
    _uninstall_setuptools(py, env)
    install = subprocess.run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            str(wheel.resolve()),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if install.returncode != 0:
        raise AssertionError(f"pip install failed: {install.stderr}")
    return py


def _install_and_verify(
    install_wheel: Path,
    pin_wheel: Path,
    *,
    plant_older: Path | None = None,
    write_pth: bool = False,
    extra_env_factory=None,
    after_install=None,
    make_old_venv: bool = False,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="rs-ha-prov-") as root:
        venv_dir = Path(root) / "venv"
        env = _sanitized_env()
        py = _create_venv_and_install(venv_dir, install_wheel, env)
        planted = None
        old_venv = None
        if plant_older is not None:
            planted = _plant_older_tree(py, venv_dir, plant_older, env)
            if write_pth:
                pth = _site_packages(py, env) / "zz_older_prepend.pth"
                pth.write_text(
                    f"import sys; sys.path.insert(0, {str(planted)!r})\n",
                    encoding="utf-8",
                )
        if make_old_venv:
            if plant_older is None:
                raise AssertionError("make_old_venv requires plant_older")
            old_venv = Path(root) / "oldvenv"
            _create_venv_and_install(old_venv, plant_older, env)
        launcher = _venv_launcher(venv_dir)
        site = _site_packages(py, env)
        if after_install is not None:
            after_install(
                _ProvHook(
                    venv_dir=venv_dir,
                    py=py,
                    launcher=launcher,
                    site=site,
                    planted=planted,
                    old_venv=old_venv,
                    env=env,
                )
            )
        if extra_env_factory:
            verify_env = extra_env_factory(venv_dir, planted, old_venv)
        else:
            verify_env = env
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
