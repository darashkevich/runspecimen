"""Opt-in --pretty / quickstart presentation must not change default JSON."""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from tests.helpers import RunSpecimenTestCase, approve, base_contract, write_contract

from runspecimen.approve import approve_contract
from runspecimen.cli import main
from runspecimen.errors import ApprovalError, PreflightError
from runspecimen.present import (
    APPROVE_BIND_PROMPT,
    format_error,
    format_pretty,
    format_quickstart,
)
from runspecimen.preflight import preflight
from runspecimen.postflight import postflight
from runspecimen.run import run_contract


class TestPresentCLI(RunSpecimenTestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_default_about_is_unchanged_json(self) -> None:
        code, out, err = self._run(["about"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertFalse(out.startswith("\033"))
        doc = json.loads(out)
        self.assertEqual(doc["product"], "RunSpecimen")
        self.assertIn("approve", doc["lifecycle"])
        self.assertIn("bounded local run", doc["summary"])
        # indent=2, sort_keys=True, trailing newline — same contract as before
        self.assertEqual(out, json.dumps(doc, indent=2, sort_keys=True) + "\n")

    def test_default_doctor_is_json_and_exit_zero(self) -> None:
        code, out, err = self._run(["doctor", "--workspace", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        doc = json.loads(out)
        self.assertTrue(doc["ok"])
        self.assertIn("user_guide", doc["docs"])
        self.assertEqual(out, json.dumps(doc, indent=2, sort_keys=True) + "\n")

    def test_pretty_doctor_is_human_and_not_json(self) -> None:
        code, out, err = self._run(
            ["--pretty", "--color", "never", "doctor", "--workspace", str(self.ws)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)
        self.assertIn("Workspace", out)
        self.assertIn(str(self.ws), out)
        self.assertNotIn("\033[", out)

        code2, out2, err2 = self._run(
            ["doctor", "--pretty", "--color", "never", "--workspace", str(self.ws)]
        )
        self.assertEqual(code2, 0)
        self.assertEqual(err2, "")
        self.assertIn("Workspace", out2)

    def test_pretty_color_always_emits_ansi_json_never_does(self) -> None:
        code, out, err = self._run(
            ["--pretty", "--color", "always", "doctor", "--workspace", str(self.ws)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("\033[", out)
        code_j, out_j, err_j = self._run(["doctor", "--workspace", str(self.ws)])
        self.assertEqual(code_j, 0)
        self.assertEqual(err_j, "")
        self.assertNotIn("\033[", out_j)

    def test_help_includes_quick_start_examples(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        self.assertIn("Quick start", text)
        self.assertIn("runspecimen init-demo", text)
        self.assertIn("--pretty", text)
        self.assertIn("JSON remains the default", text)

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                main(["approve", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Examples:", out.getvalue())
        self.assertIn("Type APPROVE", out.getvalue())

    def test_quickstart_is_human_and_mentions_tty_approve(self) -> None:
        code, out, err = self._run(["quickstart"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("Type APPROVE yourself", out)
        self.assertIn("init-demo", out)
        self.assertIn(format_quickstart().splitlines()[0], out.splitlines()[0])
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_missing_command_still_exits_two_and_points_at_quickstart(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                main([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("quickstart", err.getvalue())
        self.assertIn("error:", err.getvalue())

    def test_default_error_line_unchanged(self) -> None:
        code, out, err = self._run(
            [
                "validate",
                "--workspace",
                str(self.ws),
                "--contract",
                str(self.ws / "missing.json"),
            ]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("RunSpecimen error:"))
        self.assertNotIn("Traceback", err)
        self.assertNotIn("What to do", err)

    def test_pretty_error_keeps_message_and_adds_hint(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        code, out, err = self._run(
            [
                "--pretty",
                "--color",
                "never",
                "preflight",
                "--workspace",
                str(self.ws),
                "--contract",
                str(cpath),
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("RunSpecimen error: no approval present; run approve first", err)
        self.assertIn("What to do", err)
        self.assertIn("runspecimen approve", err)
        text = format_error(
            "no approval present; run approve first", pretty=False, color_mode="never"
        )
        self.assertEqual(text, "RunSpecimen error: no approval present; run approve first")

    def test_approve_prompt_keeps_mas_bind_line(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        stdout = io.StringIO()
        stdin = io.StringIO("nope\n")
        with self.assertRaises(ApprovalError) as ctx:
            approve_contract(
                contract_path=cpath,
                workspace=self.ws,
                stdin=stdin,
                stdout=stdout,
                skip_tty_check=True,
            )
        prompt = stdout.getvalue()
        self.assertIn(APPROVE_BIND_PROMPT, prompt)
        self.assertTrue(prompt.endswith("Type 'APPROVE' to bind this approval: "))
        self.assertIn("Command", prompt)
        self.assertIn("Fingerprints", prompt)
        self.assertIn("Agents and plugins cannot approve through the app", prompt)
        self.assertIn("confirmation phrase mismatch", str(ctx.exception))

    def test_default_verify_json_and_pretty_receipt(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        postflight(contract_path=cpath, workspace=self.ws)

        code, out, err = self._run(
            [
                "verify",
                "--workspace",
                str(self.ws),
                "--contract",
                str(cpath),
                "--campaign-id",
                "camp",
                "--run-id",
                "run-a",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        doc = json.loads(out)
        self.assertTrue(doc["ok"])
        self.assertIn("certificate_id", doc)
        self.assertEqual(out, json.dumps(doc, indent=2, sort_keys=True) + "\n")

        code_p, out_p, err_p = self._run(
            [
                "--pretty",
                "--color",
                "never",
                "verify",
                "--workspace",
                str(self.ws),
                "--contract",
                str(cpath),
                "--campaign-id",
                "camp",
                "--run-id",
                "run-a",
            ]
        )
        self.assertEqual(code_p, 0)
        self.assertEqual(err_p, "")
        self.assertIn("Receipt verification (files/chain; not signatures)", out_p)
        self.assertIn("verify-signature", out_p)
        self.assertIn("trust inputs", out_p)
        self.assertNotIn("OK  Live receipt verification", out_p)
        self.assertIn(doc["certificate_id"], out_p)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out_p)

        code_s, out_s, _ = self._run(
            [
                "status",
                "--workspace",
                str(self.ws),
                "--campaign-id",
                "camp",
                "--run-id",
                "run-a",
            ]
        )
        self.assertEqual(code_s, 0)
        status_doc = json.loads(out_s)
        self.assertEqual(status_doc["phase"], "postflighted")

        code_sp, out_sp, _ = self._run(
            [
                "status",
                "--pretty",
                "--color",
                "never",
                "--workspace",
                str(self.ws),
                "--campaign-id",
                "camp",
                "--run-id",
                "run-a",
            ]
        )
        self.assertEqual(code_sp, 0)
        self.assertIn("Postflight recorded", out_sp)
        self.assertIn("not live verify", out_sp.lower())

        code_d, out_d, _ = self._run(
            [
                "--pretty",
                "--color",
                "never",
                "digest",
                "--workspace",
                str(self.ws),
                "--campaign-id",
                "camp",
                "--run-id",
                "run-a",
            ]
        )
        self.assertEqual(code_d, 0)
        self.assertIn("not verify", out_d.lower())
        self.assertIn("outputs/out.json", out_d)

    def test_pretty_does_not_change_preflight_refusal_exit_code(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        with self.assertRaises(PreflightError):
            preflight(contract_path=cpath, workspace=self.ws)
        code, _, err = self._run(
            ["preflight", "--workspace", str(self.ws), "--contract", str(cpath)]
        )
        self.assertEqual(code, 1)
        self.assertIn("no approval present", err)
        code_p, _, err_p = self._run(
            [
                "preflight",
                "--pretty",
                "--workspace",
                str(self.ws),
                "--contract",
                str(cpath),
            ]
        )
        self.assertEqual(code_p, 1)
        self.assertIn("no approval present", err_p)

    def test_pretty_holder_policy_hint_does_not_say_use_the_holder(self) -> None:
        text = format_error(
            "execution policy local has no typed-phrase fallback",
            pretty=True,
            color_mode="never",
        )
        first = text.splitlines()[0]
        self.assertEqual(
            first,
            "RunSpecimen error: execution policy local has no typed-phrase fallback",
        )
        self.assertIn(
            "Holder policies need a separately qualified holder; typed-phrase approval isn't available here.",
            text,
        )
        self.assertNotIn("Use the holder", text)

    def test_pretty_verify_incomplete_payload_is_not_success(self) -> None:
        out = format_pretty(
            {"campaign_id": "camp", "run_id": "run-a"},
            kind="verify",
            color_mode="never",
        )
        self.assertIn("REFUSED", out)
        self.assertIn("Receipt verification failed", out)
        self.assertNotIn("OK  ", out)
        self.assertIn("verify-signature", out)

    def test_pretty_verify_ok_false_is_not_success(self) -> None:
        out = format_pretty(
            {"ok": False, "campaign_id": "camp", "run_id": "run-a"},
            kind="verify",
            color_mode="never",
        )
        self.assertIn("REFUSED", out)
        self.assertIn("Receipt verification failed", out)
        self.assertNotIn("OK  ", out)

    def test_pretty_verify_non_boolean_ok_is_not_success(self) -> None:
        for value in ("true", 1, "yes", None):
            with self.subTest(ok=value):
                out = format_pretty(
                    {"ok": value, "campaign_id": "camp"},
                    kind="verify",
                    color_mode="never",
                )
                self.assertIn("REFUSED", out)
                self.assertNotIn("OK  ", out)

    def test_pretty_never_defaults_ok_to_true_in_source(self) -> None:
        from pathlib import Path

        import runspecimen.present as present_mod

        text = Path(present_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn('get("ok", True)', text)
        self.assertNotIn("get('ok', True)", text)
        self.assertIn("def _strict_ok", text)

    def test_pretty_verify_tampered_workspace_fails_nonzero(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        postflight(contract_path=cpath, workspace=self.ws)
        output = self.ws / "outputs" / "out.json"
        output.write_text('{"status": "tampered"}\n', encoding="utf-8")

        code, out, err = self._run(
            [
                "--pretty",
                "--color",
                "never",
                "verify",
                "--workspace",
                str(self.ws),
                "--contract",
                str(cpath),
                "--campaign-id",
                "camp",
                "--run-id",
                "run-a",
            ]
        )
        self.assertNotEqual(code, 0)
        self.assertTrue(err.startswith("RunSpecimen error:"))
        self.assertNotIn("OK  ", out)
        self.assertNotIn("Receipt verification (files/chain; not signatures)", out)

    def test_no_color_env_disables_auto_color(self) -> None:
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        with patch.dict(os.environ, env, clear=False):
            code, out, _ = self._run(
                ["--pretty", "--color", "auto", "doctor", "--workspace", str(self.ws)]
            )
        self.assertEqual(code, 0)
        self.assertNotIn("\033[", out)


if __name__ == "__main__":
    unittest.main()
