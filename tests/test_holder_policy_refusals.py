"""RS-02 / RS-03 / RS-04: holder policies refuse the typed phrase the same way."""

from __future__ import annotations

import os
import subprocess
import unittest
from io import StringIO

from tests.helpers import (
    PYTHON,
    SRC,
    NullWriter,
    PhraseReader,
    RunSpecimenTestCase,
    base_contract,
    write_contract,
)

from runspecimen.approve import (
    approve_contract,
    typed_phrase_fallback_refusal,
)
from runspecimen.errors import ApprovalError, PostflightError, PreflightError
from runspecimen.paths import ensure_dir, run_state_dir
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.state import update_state

_POLICIES = ("local", "companion", "dual")
_HOLDER_MARK = "authorized from the holder"
_FALLBACK_MARK = "no typed-phrase fallback"
_TTY_MARK = "interactive tty"


class _PipedIO:
    """Non-TTY streams, as when approve is piped."""

    def isatty(self) -> bool:
        return False

    def readline(self) -> str:
        raise AssertionError("piped approve must not read a confirmation phrase")

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        return None


class TestSharedHolderRefusalSentence(unittest.TestCase):
    def test_sentence_is_plain_english_and_names_the_policy(self) -> None:
        for policy in _POLICIES:
            message = typed_phrase_fallback_refusal(policy)
            self.assertIn(_HOLDER_MARK, message)
            self.assertIn(_FALLBACK_MARK, message)
            self.assertIn(f"({policy})", message)
            self.assertNotIn("run approve first", message)


class TestPreflightPostflightHolderPolicy(RunSpecimenTestCase):
    def test_ordinary_contract_still_asks_to_approve_first(self) -> None:
        path = write_contract(self.ws, "ordinary.json", base_contract())
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=path, workspace=self.ws)
        self.assertIn("run approve first", str(ctx.exception))
        self.assertNotIn(_HOLDER_MARK, str(ctx.exception))

    def test_preflight_refuses_holder_policies_without_suggesting_approve(self) -> None:
        for policy in _POLICIES:
            with self.subTest(policy=policy):
                path = write_contract(
                    self.ws, f"{policy}.json", base_contract(execution_approval=policy)
                )
                with self.assertRaises(PreflightError) as ctx:
                    preflight(contract_path=path, workspace=self.ws)
                message = str(ctx.exception)
                self.assertEqual(message, typed_phrase_fallback_refusal(policy))
                self.assertNotIn("run approve first", message)

    def test_preflight_does_not_accept_a_planted_workspace_approval(self) -> None:
        path = write_contract(
            self.ws, "planted.json", base_contract(execution_approval="local")
        )
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        ensure_dir(state_dir)
        (state_dir / "approval.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=path, workspace=self.ws)
        self.assertEqual(str(ctx.exception), typed_phrase_fallback_refusal("local"))

    def test_postflight_refuses_holder_policies_at_the_provenance_gate(self) -> None:
        for policy in _POLICIES:
            with self.subTest(policy=policy):
                path = write_contract(
                    self.ws,
                    f"post-{policy}.json",
                    base_contract(execution_approval=policy, run_id=f"run-{policy}"),
                )
                state_dir = run_state_dir(self.ws, "camp", f"run-{policy}")
                ensure_dir(state_dir)
                update_state(
                    state_dir,
                    phase="completed",
                    run_result="completed",
                    exit_code=0,
                )
                with self.assertRaises(PostflightError) as ctx:
                    postflight(contract_path=path, workspace=self.ws)
                message = str(ctx.exception)
                self.assertEqual(message, typed_phrase_fallback_refusal(policy))
                self.assertNotIn("run approve first", message)
                self.assertNotIn("cannot verify contract provenance", message)


class TestApprovePolicyBeforeTty(RunSpecimenTestCase):
    def test_piped_and_pty_print_the_same_holder_sentence(self) -> None:
        path = write_contract(
            self.ws, "c.json", base_contract(execution_approval="local")
        )
        expected = typed_phrase_fallback_refusal("local")
        piped = _PipedIO()
        with self.assertRaises(ApprovalError) as piped_ctx:
            approve_contract(
                contract_path=path,
                workspace=self.ws,
                stdin=piped,
                stdout=piped,
            )
        self.assertEqual(str(piped_ctx.exception), expected)
        self.assertNotIn(_TTY_MARK, str(piped_ctx.exception).lower())

        pty_in = PhraseReader("APPROVE\n")
        pty_out = NullWriter()
        self.assertTrue(pty_in.isatty())
        self.assertTrue(pty_out.isatty())
        with self.assertRaises(ApprovalError) as pty_ctx:
            approve_contract(
                contract_path=path,
                workspace=self.ws,
                stdin=pty_in,
                stdout=pty_out,
            )
        self.assertEqual(str(pty_ctx.exception), expected)
        self.assertEqual(str(piped_ctx.exception), str(pty_ctx.exception))
        self.assertEqual(pty_in._pos, 0)

    def test_piped_ordinary_contract_still_requires_a_tty(self) -> None:
        path = write_contract(self.ws, "ordinary.json", base_contract())
        piped = StringIO("APPROVE\n")
        with self.assertRaises(ApprovalError) as ctx:
            approve_contract(
                contract_path=path,
                workspace=self.ws,
                stdin=piped,
                stdout=StringIO(),
            )
        self.assertIn(_TTY_MARK, str(ctx.exception).lower())
        self.assertNotIn(_HOLDER_MARK, str(ctx.exception))

    def test_cli_piped_and_pty_print_the_same_holder_sentence(self) -> None:
        path = write_contract(
            self.ws, "cli.json", base_contract(execution_approval="companion")
        )
        expected = typed_phrase_fallback_refusal("companion")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        piped = subprocess.run(
            [
                PYTHON,
                "-m",
                "runspecimen",
                "approve",
                "--workspace",
                str(self.ws),
                "--contract",
                str(path),
            ],
            cwd=str(self.ws),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(piped.returncode, 0)
        self.assertIn(expected, piped.stderr)
        self.assertNotIn("interactive tty", piped.stderr.lower())

        master_fd, slave_fd = os.openpty()
        try:
            pty_proc = subprocess.Popen(
                [
                    PYTHON,
                    "-m",
                    "runspecimen",
                    "approve",
                    "--workspace",
                    str(self.ws),
                    "--contract",
                    str(path),
                ],
                cwd=str(self.ws),
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=subprocess.PIPE,
                text=True,
            )
            os.close(slave_fd)
            slave_fd = -1
            stderr = pty_proc.communicate(timeout=30)[1]
        finally:
            os.close(master_fd)
            if slave_fd >= 0:
                os.close(slave_fd)
        self.assertNotEqual(pty_proc.returncode, 0)
        self.assertIn(expected, stderr)
        self.assertEqual(
            expected in piped.stderr,
            expected in stderr,
        )


class TestApproveClaimWording(RunSpecimenTestCase):
    def test_local_tty_claim_is_os_neutral(self) -> None:
        path = write_contract(self.ws, "c.json", base_contract())
        doc = approve_contract(
            contract_path=path,
            workspace=self.ws,
            skip_tty_check=True,
            stdin=PhraseReader("APPROVE\n"),
            stdout=NullWriter(),
        )
        claim = doc["confirm_evidence"]["claim"]
        self.assertEqual(claim, "Interactive local TTY APPROVE on this computer.")
        self.assertNotIn("on the Mac", claim)


if __name__ == "__main__":
    unittest.main()
