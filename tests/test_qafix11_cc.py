"""ChatGPT QA #5 (CC-01..CC-06) regressions for unpublished 0.2.0rc15 qafix11."""

from __future__ import annotations

import json
import os
import py_compile
import sys
import tempfile
import unittest
import venv
from pathlib import Path

from tests.helpers import ROOT, SRC, base_contract, write_contract
from tests.test_cli_signing import _create_valid_run, _run_cli
from tests.test_rc15_qafix_docs import (
    VERIFY_INSTALLED,
    _create_venv_and_install,
    _install_and_verify,
    _load_verify_module,
    _pin_wheel,
    _sanitized_env,
    _venv_launcher,
    _venv_python,
)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.contract import load_contract
from runspecimen.errors import ContractError
from runspecimen.present import (
    APPROVE_BIND_PROMPT,
    escape_for_terminal,
    format_approve_prompt,
    format_error,
    format_pretty,
)
from runspecimen.terminaltext import has_unsafe_display_chars


ESC = "\x1b"
CSI = "\x1b[2J\x1b[H"
OSC = "\x1b]0;hijack\x07"
CR = "\r"
BS = "\x08"
BIDI = "\u202e"
NUL = "\x00"


def _prompt(**overrides: object) -> str:
    kwargs = {
        "campaign_id": "camp",
        "run_id": "run-a",
        "argv": [sys.executable, "work/job.py"],
        "cwd": ".",
        "sources": ["work"],
        "excludes": [],
        "outputs": ["outputs/out.json"],
        "timeout_sec": 10,
        "stdout_max_bytes": 65536,
        "stderr_max_bytes": 65536,
        "predecessor": None,
        "isolation_claim": "none",
        "policy_line": "none",
        "approver_user": "tester",
        "contract_hash": "a" * 64,
        "source_hash": "b" * 64,
        "runtime_path": sys.executable,
        "runtime_id": "c" * 64,
        "ttl_sec": 3600,
        "confirm_phrase": "APPROVE",
    }
    kwargs.update(overrides)
    return format_approve_prompt(**kwargs)  # type: ignore[arg-type]


class CC01TerminalControlTests(unittest.TestCase):
    def test_n10_and_unknown_field_error_bytes_unchanged(self) -> None:
        n10 = "execution policy local has no typed-phrase fallback"
        unk = "contract contains unknown field(s): not_a_real_contract_field"
        self.assertEqual(
            format_error(n10, pretty=False).encode("utf-8"),
            b"RunSpecimen error: execution policy local has no typed-phrase fallback",
        )
        self.assertEqual(
            format_error(unk, pretty=False).encode("utf-8"),
            b"RunSpecimen error: contract contains unknown field(s): not_a_real_contract_field",
        )

    def test_bind_line_unchanged_when_argv_is_escaped(self) -> None:
        prompt = _prompt(argv=["/bin/echo", CSI])
        self.assertTrue(prompt.endswith("Type 'APPROVE' to bind this approval: "))
        self.assertIn(APPROVE_BIND_PROMPT, prompt)
        raw = prompt.encode("utf-8")
        self.assertNotIn(b"\x1b", raw)
        self.assertIn(b"\\x1b", raw)

    def test_rendered_bytes_escape_esc_csi_osc_cr_bs_bidi_nul(self) -> None:
        cases = {
            "esc": ESC,
            "csi": CSI,
            "osc": OSC,
            "cr": CR,
            "bs": BS,
            "bidi": BIDI,
            "nul": NUL,
        }
        for name, payload in cases.items():
            with self.subTest(name=name, where="argv"):
                raw = _prompt(argv=["/bin/echo", payload]).encode("utf-8")
                self.assertNotIn(payload.encode("utf-8"), raw)
                self.assertIn(escape_for_terminal(payload).encode("utf-8"), raw)
            with self.subTest(name=name, where="cwd"):
                raw = _prompt(cwd=f".{payload}dir" if payload != NUL else ".\x00dir").encode("utf-8")
                self.assertNotIn(payload.encode("utf-8"), raw)
            with self.subTest(name=name, where="campaign"):
                raw = _prompt(campaign_id=f"camp{payload}").encode("utf-8")
                self.assertNotIn(payload.encode("utf-8"), raw)
            with self.subTest(name=name, where="run"):
                raw = _prompt(run_id=f"run{payload}").encode("utf-8")
                self.assertNotIn(payload.encode("utf-8"), raw)
            with self.subTest(name=name, where="env"):
                text = format_pretty(
                    {"ok": True, "env": {"SECRET": payload}},
                    kind="remote-confirm",
                    color_mode="never",
                )
                raw = text.encode("utf-8")
                self.assertNotIn(payload.encode("utf-8"), raw)

    def test_contract_refuses_controls_in_argv_cwd_env_and_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-cc01-") as raw:
            ws = Path(raw)
            (ws / "work").mkdir()
            cases = [
                ("argv", {"argv": [sys.executable, CSI]}),
                ("cwd", {"cwd": f"./{CR}here"}),
                ("env", {"runtime": {"env_allowlist": [f"FOO{BS}"]}}),
                ("campaign_id", {"campaign_id": f"camp{BIDI}"}),
                ("run_id", {"run_id": f"run{ESC}"}),
                ("argv_nul", {"argv": [sys.executable, f"x{NUL}y"]}),
            ]
            for label, override in cases:
                doc = base_contract(**override)
                path = write_contract(ws, f"{label}.json", doc)
                with self.subTest(label=label):
                    with self.assertRaises(ContractError) as ctx:
                        load_contract(path)
                    msg = str(ctx.exception).lower()
                    self.assertTrue(
                        "terminal control" in msg
                        or "nul bytes" in msg
                        or "unsafe id" in msg,
                        msg,
                    )


class CC02ShebangParentIdentityTests(unittest.TestCase):
    def test_cc02_default_tmpdir_venv_shebang_is_accepted(self) -> None:
        """Must run on macOS CI with the process default TMPDIR (no override)."""
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        # Intentionally do not set or rewrite TMPDIR. Compare parents while
        # the venv directory still exists; TemporaryDirectory removal makes
        # samefile fail even when the paths were the same directory.
        checked: dict[str, bool] = {}

        def _inspect(result: subprocess.CompletedProcess[str]) -> None:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout.split("---")[0])
            self.assertTrue(payload["ok"], payload)
            shebang_parent = Path(payload["interpreter"]).parent
            launcher_parent = Path(payload["launcher"]).parent
            if shebang_parent != launcher_parent:
                self.assertTrue(
                    shebang_parent.samefile(launcher_parent),
                    (str(shebang_parent), str(launcher_parent)),
                )
            checked["samefile"] = True

        result = _install_and_verify(pin, pin, inspect=_inspect)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(checked.get("samefile"))

    def test_cc02_symlinked_parent_dirs_are_accepted(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-cc02-alias-") as raw:
            root = Path(raw)
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real)
            venv_dir = real / "venv"
            env = _sanitized_env()
            _create_venv_and_install(venv_dir, pin, env)
            launcher = alias / "venv" / "bin" / "runspecimen"
            interpreter = module.interpreter_from_launcher(launcher)
            self.assertTrue(interpreter.parent.samefile(launcher.parent))

    def test_cc02_other_venv_sharing_base_python_is_refused(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-cc02-other-") as raw:
            root = Path(raw)
            env = _sanitized_env()
            a = root / "a"
            b = root / "b"
            _create_venv_and_install(a, pin, env)
            venv.create(b, with_pip=False, symlinks=True)
            launcher = _venv_launcher(a)
            other_py = _venv_python(b)
            text = launcher.read_text(encoding="utf-8")
            lines = text.splitlines(True)
            lines[0] = f"#!{other_py}\n"
            launcher.write_text("".join(lines), encoding="utf-8")
            with self.assertRaises(module.UnsupportedShebangError) as ctx:
                module.interpreter_from_launcher(launcher)
            self.assertIn("not this venv's own Python", str(ctx.exception))


class CC03PrettyVerifySignatureTests(unittest.TestCase):
    def test_pretty_mac_valid_receipt_invalid_leads_with_receipt_error(self) -> None:
        payload = {
            "ok": False,
            "scheme": "hmac",
            "mac_valid": True,
            "schema_valid": True,
            "receipt_valid": False,
            "canonical_match": True,
            "message": "MAC valid, schema valid",
            "receipt_verification_error": "state.json missing (deleted or never written)",
            "key_id": "test-key",
        }
        text = format_pretty(payload, kind="verify-signature", color_mode="never")
        self.assertIn("REFUSED", text)
        self.assertIn("state.json missing (deleted or never written)", text)
        first = text.split("Receipt error", 1)[0]
        self.assertNotIn("MAC valid, schema valid", first)
        self.assertLess(text.find("Receipt error"), text.find("MAC valid"))

    def test_cli_pretty_verify_signature_missing_state_shows_explanatory_text(self) -> None:
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            contract_path, campaign_id, run_id = _create_valid_run(workspace)
            from runspecimen.signing import SigningKey, save_signing_key

            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)
            state_dir = workspace / ".runspecimen" / "runs" / campaign_id / run_id
            cert_path = state_dir / "certificate.json"
            rc, stdout, stderr = _run_cli(
                "sign",
                "--workspace",
                str(workspace),
                "--key-id",
                "test-key",
                "--certificate",
                str(cert_path),
                "--contract",
                str(contract_path),
            )
            self.assertEqual(rc, 0, stderr)
            signed_path = json.loads(stdout)["signed_output"]
            (state_dir / "state.json").unlink()
            rc, stdout, stderr = _run_cli(
                "--pretty",
                "--color",
                "never",
                "verify-signature",
                "--workspace",
                str(workspace),
                "--key-id",
                "test-key",
                "--signed",
                signed_path,
                "--contract",
                str(contract_path),
            )
            self.assertNotEqual(rc, 0)
            combined = stdout + stderr
            self.assertIn("REFUSED", combined)
            self.assertIn("state.json missing (deleted or never written)", combined)
            self.assertTrue(
                combined.find("state.json missing")
                < combined.lower().find("mac valid, certificate matches")
                or "MAC valid, certificate matches" not in combined
            )


class CC04LauncherTemplateTests(unittest.TestCase):
    def test_pinned_templates_are_exact_known_bodies(self) -> None:
        module = _load_verify_module()
        distlib = (
            b"# -*- coding: utf-8 -*-\n"
            b"import re\n"
            b"import sys\n"
            b"from runspecimen.cli import main\n"
            b"if __name__ == '__main__':\n"
            b"    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
            b"    sys.exit(main())\n"
        )
        endswith = (
            b"import sys\n"
            b"from runspecimen.cli import main\n"
            b"if __name__ == '__main__':\n"
            b"    if sys.argv[0].endswith('.exe'):\n"
            b"        sys.argv[0] = sys.argv[0][:-4]\n"
            b"    sys.exit(main())\n"
        )
        removesuffix = (
            b"import sys\n"
            b"from runspecimen.cli import main\n"
            b"if __name__ == '__main__':\n"
            b"    sys.argv[0] = sys.argv[0].removesuffix('.exe')\n"
            b"    sys.exit(main())\n"
        )
        self.assertEqual(module.PIP_DISTLIB_CONSOLE_SCRIPT_BODY, distlib)
        self.assertEqual(module.PIP_SCRIPTMAKER_ENDSWITH_BODY, endswith)
        self.assertEqual(module.PIP_SCRIPTMAKER_REMOVESUFFIX_BODY, removesuffix)
        self.assertEqual(
            module.KNOWN_CONSOLE_SCRIPT_BODIES,
            (distlib, endswith, removesuffix),
        )
        self.assertEqual(len(set(module.KNOWN_CONSOLE_SCRIPT_BODIES)), 3)

    def test_pinned_template_matches_real_pip_body(self) -> None:
        module = _load_verify_module()
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        with tempfile.TemporaryDirectory(prefix="rs-cc04-pip-") as raw:
            env = _sanitized_env()
            venv_dir = Path(raw) / "venv"
            _create_venv_and_install(venv_dir, pin, env)
            launcher = _venv_launcher(venv_dir)
            data = launcher.read_bytes()
            body = module.launcher_body_after_shebang(data)
            self.assertIn(body, module.KNOWN_CONSOLE_SCRIPT_BODIES)
            self.assertEqual(module.console_script_target(launcher), "runspecimen.cli:main")

    def test_import_main_without_calling_it_is_refused(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")

        def _rewrite_no_call(hook: object) -> None:
            launcher = hook.launcher  # type: ignore[attr-defined]
            text = launcher.read_text(encoding="utf-8")
            lines = text.splitlines(True)
            shebang = lines[0]
            fake = (
                shebang
                + "from runspecimen.cli import main\n"
                + "print('forged-about')\n"
            )
            launcher.write_text(fake, encoding="utf-8")

        result = _install_and_verify(pin, pin, after_install=_rewrite_no_call)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pinned pip template", result.stdout + result.stderr)


class CC05BytecodeRefusalTests(unittest.TestCase):
    def _plant_pyc(self, hook: object, *, hash_based: bool) -> None:
        site = hook.site  # type: ignore[attr-defined]
        cli = site / "runspecimen" / "cli.py"
        original = cli.read_bytes()
        hijack = original + b"\n# hijack\n"
        cli.write_bytes(hijack)
        kwargs = {"doraise": True}
        if hash_based:
            kwargs["invalidation_mode"] = py_compile.PycInvalidationMode.UNCHECKED_HASH
        py_compile.compile(str(cli), **kwargs)
        cache = cli.parent / "__pycache__"
        pycs = list(cache.glob("cli*.pyc"))
        if not pycs:
            raise AssertionError(f"no pyc produced under {cache}")
        pyc = pycs[0]
        cli.write_bytes(original)
        os.utime(cli, (pyc.stat().st_mtime - 30, pyc.stat().st_mtime - 30))
        os.utime(pyc, (pyc.stat().st_mtime + 30, pyc.stat().st_mtime + 30))

    def test_timestamp_pyc_under_package_is_refused(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")

        def plant(hook: object) -> None:
            self._plant_pyc(hook, hash_based=False)

        result = _install_and_verify(pin, pin, after_install=plant)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("bytecode", (result.stdout + result.stderr).lower())

    def test_hash_based_pyc_under_package_is_refused(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")

        def plant(hook: object) -> None:
            self._plant_pyc(hook, hash_based=True)

        result = _install_and_verify(pin, pin, after_install=plant)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("bytecode", (result.stdout + result.stderr).lower())

    def test_pythonpycacheprefix_is_refused(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")

        def extra(venv_dir: Path, planted: Path | None, old_venv: Path | None) -> dict[str, str]:
            env = _sanitized_env()
            env["PYTHONPYCACHEPREFIX"] = str(venv_dir / "ext-pycache")
            return env

        result = _install_and_verify(pin, pin, extra_env_factory=extra)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PYTHONPYCACHEPREFIX", result.stdout + result.stderr)


class CC06HonestyWordingTests(unittest.TestCase):
    def test_protect_against_that_sign_receipts_is_gone(self) -> None:
        forbidden = "To protect against that, sign receipts"
        hits = []
        for root in (ROOT / "src", ROOT / "docs", ROOT / "README.md", ROOT / "CHANGELOG.md"):
            paths = [root] if root.is_file() else list(root.rglob("*.md")) + list(root.rglob("*.py"))
            for path in paths:
                if path.name == "BIOMETRIC_APPROVAL.md":
                    continue
                text = path.read_text(encoding="utf-8")
                if forbidden in text:
                    hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_signing_limit_wording_is_present(self) -> None:
        needle = (
            "Signing with a key the agent can't access lets you check afterwards "
            "that a receipt is authentic, when a signature is required and checked"
        )
        limit = "it does not stop a program running as you from adding a fake approval or running the job"
        for rel in (
            "README.md",
            "CHANGELOG.md",
            "docs/FAQ.md",
            "docs/ABOUT.md",
            "docs/THREAT_MODEL.md",
            "docs/USER_GUIDE.md",
            "src/runspecimen/cli.py",
            "src/runspecimen/present.py",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            collapsed = " ".join(text.split())
            with self.subTest(rel=rel):
                self.assertIn(needle, collapsed)
                self.assertIn(limit, collapsed)


class TerminalTextUnitTests(unittest.TestCase):
    def test_unsafe_classifier_and_escape(self) -> None:
        self.assertTrue(has_unsafe_display_chars(CSI))
        self.assertTrue(has_unsafe_display_chars(BIDI))
        self.assertEqual(escape_for_terminal("\x1b"), "\\x1b")
        self.assertEqual(escape_for_terminal("\u202e"), "\\u202e")
        self.assertEqual(escape_for_terminal("plain"), "plain")


if __name__ == "__main__":
    unittest.main()
