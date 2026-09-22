"""Opt-in bubblewrap confinement on Linux.

``bwrap`` confines writes and, by default, network. It is not an OS sandbox.
Discovery, validate, approve, preflight, doctor, and ``runspecimen isolation``
hash or locate the tool and must not execute it. A missing declared backend
fails closed before spawn.
"""

from __future__ import annotations

import contextlib
import errno
import io
import json
import os
import shlex
import shutil
import socket
import sys
import textwrap
import unittest
from pathlib import Path
from typing import Any

from tests.helpers import (
    SRC,
    RunSpecimenTestCase,
    approve,
    base_contract,
    write_contract,
)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.approve import load_approval
from runspecimen.certificate import load_certificate
from runspecimen.cli import main
from runspecimen.contract import IsolationSpec, load_contract
from runspecimen.errors import PostflightError, PreflightError
from runspecimen.hashutil import sha256_file
from runspecimen.isolation import (
    confinement_argv,
    discover_tool,
    effective_plan,
    host_capabilities,
    plans_match,
)
from runspecimen.paths import STDERR_FILENAME, STDOUT_FILENAME, run_state_dir
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.state import load_state

ESCAPE_PATH = Path("/tmp/runspecimen-bwrap-escape")


def _option_pairs(argv: list[str], flag: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(argv):
        if item == flag:
            pairs.append((argv[index + 1], argv[index + 2]))
    return pairs


def _assert_enforced_bwrap_receipt(case: unittest.TestCase, receipt: dict[str, Any]) -> None:
    case.assertEqual(receipt.get("backend"), "bwrap")
    case.assertIs(receipt.get("enforced"), True)
    case.assertEqual(receipt.get("network"), "denied")
    case.assertIn("bubblewrap", str(receipt.get("claim")))
    case.assertNotIn("OS sandbox", str(receipt.get("claim")))
    case.assertIn("Not an OS sandbox", str(receipt.get("residual")))
    case.assertNotIn("is an OS sandbox", json.dumps(receipt))


class BwrapConstructionTests(RunSpecimenTestCase):
    def _plant_bwrap(self) -> tuple[Path, Path]:
        bin_dir = self.ws.parent / f"bwrap-bin-{self.ws.name}"
        bin_dir.mkdir()
        marker = self.ws.parent / f"bwrap-executed-{self.ws.name}"
        tool = bin_dir / "bwrap"
        tool.write_text(
            "#!/bin/sh\n" + f"echo executed > {shlex.quote(str(marker))}\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
        previous = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + previous
        self.addCleanup(lambda: os.environ.__setitem__("PATH", previous))
        self.addCleanup(lambda: shutil.rmtree(bin_dir, ignore_errors=True))
        self.addCleanup(marker.unlink, missing_ok=True)
        return tool, marker

    def _cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_default_argv_denies_network_binds_workspace_and_does_not_execute(self) -> None:
        tool, marker = self._plant_bwrap()
        self.assertNotIn(self.ws.resolve(), tool.resolve().parents)
        path = write_contract(self.ws, "c.json", base_contract(isolation={"backend": "bwrap"}))
        contract = load_contract(path)
        self.assertFalse(contract.isolation.network)

        code, validate_out, validate_err = self._cli(
            ["validate", "--workspace", str(self.ws), "--contract", str(path)]
        )
        self.assertEqual(code, 0, validate_err)
        self.assertFalse(marker.exists(), "validate executed the isolation tool")
        _assert_enforced_bwrap_receipt(self, json.loads(validate_out)["isolation"])

        for argv in (
            ["doctor", "--workspace", str(self.ws)],
            ["isolation"],
        ):
            code, _out, err = self._cli(argv)
            self.assertEqual(code, 0, err)
            self.assertFalse(marker.exists(), f"{argv[0]} executed the isolation tool")

        approve(self.ws, path)
        self.assertFalse(marker.exists(), "approve executed the isolation tool")
        code, _out, err = self._cli(
            ["preflight", "--workspace", str(self.ws), "--contract", str(path)]
        )
        self.assertEqual(code, 0, err)
        self.assertFalse(marker.exists(), "preflight executed the isolation tool")

        plan = effective_plan(contract.isolation)
        _assert_enforced_bwrap_receipt(self, plan)
        self.assertEqual(plan["tool"], str(tool.resolve()))
        self.assertEqual(plan["tool_sha256"], sha256_file(tool))
        workspace = self.ws.resolve()
        profile = self.ws / "isolation.sb"
        argv = confinement_argv(
            plan,
            [sys.executable, "work/job.py"],
            workspace=workspace,
            cwd=workspace,
            profile_path=profile,
        )
        self.assertFalse(marker.exists(), "constructing argv executed the isolation tool")
        self.assertFalse(profile.exists())
        self.assertEqual(argv[0], plan["tool"])
        separator = argv.index("--")
        self.assertIn("--unshare-net", argv[:separator])
        self.assertIn(("/", "/"), _option_pairs(argv, "--ro-bind"))
        self.assertNotIn(("/", "/"), _option_pairs(argv, "--bind"))
        self.assertIn((str(workspace), str(workspace)), _option_pairs(argv, "--bind"))
        self.assertEqual(argv[separator + 1 :], [sys.executable, "work/job.py"])
        self.assertNotIn("shell", argv)


class BwrapMissingBackendTests(RunSpecimenTestCase):
    def test_missing_bwrap_fails_closed_before_spawn(self) -> None:
        empty = self.ws.parent / f"no-bwrap-{self.ws.name}"
        empty.mkdir()
        previous = os.environ.get("PATH", "")
        os.environ["PATH"] = str(empty)
        self.addCleanup(lambda: os.environ.__setitem__("PATH", previous))
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))

        self.assertIsNone(shutil.which("bwrap"))
        self.assertIsNone(discover_tool("bwrap"))
        with self.assertRaises(PreflightError) as ctx:
            effective_plan(IsolationSpec(backend="bwrap"))
        self.assertIn("not available", str(ctx.exception))

        path = write_contract(self.ws, "c.json", base_contract(isolation={"backend": "bwrap"}))
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["validate", "--workspace", str(self.ws), "--contract", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("not available", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

        with self.assertRaises(PreflightError) as ctx:
            approve(self.ws, path)
        self.assertIn("not available", str(ctx.exception))

        state_dir = run_state_dir(self.ws, "camp", "run-a")
        self.assertFalse((state_dir / "state.json").exists())
        self.assertFalse((state_dir / "approval.json").exists())
        self.assertFalse((state_dir / "certificate.json").exists())
        self.assertFalse((state_dir / STDOUT_FILENAME).exists())
        self.assertIsNone(load_certificate(state_dir))


@unittest.skipUnless(
    shutil.which("bwrap"),
    "bwrap is not installed; real confinement spawn skipped",
)
class BwrapLinuxIntegrationTests(RunSpecimenTestCase):
    def test_outside_write_is_blocked_and_not_certified(self) -> None:
        ESCAPE_PATH.unlink(missing_ok=True)
        self.addCleanup(ESCAPE_PATH.unlink, missing_ok=True)
        self.assertFalse(self.ws.resolve() in ESCAPE_PATH.resolve().parents)

        # Exit 0 and the required output happen only if the outside write
        # succeeds. Confinement is supposed to stop that write, so postflight
        # must not issue a success certificate.
        job = textwrap.dedent(
            """\
            import pathlib
            import sys

            pathlib.Path("outputs/ran.txt").write_text("payload-ran\\n", encoding="utf-8")
            target = pathlib.Path("/tmp/runspecimen-bwrap-escape")
            try:
                target.write_text("escaped\\n", encoding="utf-8")
            except OSError as exc:
                print(f"outside-write-denied errno={exc.errno}", flush=True)
                sys.exit(3)
            pathlib.Path("outputs/out.json").write_text('{"status":"ok"}\\n', encoding="utf-8")
            print("outside-write-succeeded", flush=True)
            sys.exit(0)
            """
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
        path = write_contract(self.ws, "c.json", base_contract(isolation={"backend": "bwrap"}))
        approve(self.ws, path)
        preflight(contract_path=path, workspace=self.ws)
        result = run_contract(contract_path=path, workspace=self.ws)

        state_dir = run_state_dir(self.ws, "camp", "run-a")
        stdout = (state_dir / STDOUT_FILENAME).read_bytes()
        stderr = (state_dir / STDERR_FILENAME).read_bytes()
        detail = f"result={result!r} stdout={stdout!r} stderr={stderr!r}"
        self.assertFalse(ESCAPE_PATH.exists(), detail)
        ran = self.ws / "outputs" / "ran.txt"
        self.assertTrue(ran.is_file(), detail)
        self.assertEqual(ran.read_text(encoding="utf-8"), "payload-ran\n")
        self.assertFalse((self.ws / "outputs" / "out.json").exists(), detail)
        self.assertIn(f"outside-write-denied errno={errno.EROFS}".encode(), stdout, detail)
        self.assertNotIn(b"outside-write-succeeded", stdout)
        self.assertEqual(result["exit_code"], 3, detail)
        self.assertIsNone(load_certificate(state_dir))

        with self.assertRaises(PostflightError) as ctx:
            postflight(contract_path=path, workspace=self.ws)
        self.assertIn("exit_code", str(ctx.exception))
        self.assertIsNone(load_certificate(state_dir))
        state = load_state(state_dir)
        self.assertEqual(state.get("phase"), "failed")

        approval = load_approval(state_dir)
        self.assertIsNotNone(approval)
        assert approval is not None
        self.assertTrue(plans_match(approval["isolation"], state["isolation"]))
        for receipt in (approval["isolation"], state["isolation"]):
            _assert_enforced_bwrap_receipt(self, receipt)
            tool = Path(receipt["tool"])
            self.assertTrue(tool.is_file())
            self.assertEqual(tool, Path(shutil.which("bwrap")).resolve())
            self.assertEqual(receipt["tool_sha256"], sha256_file(tool))



class BwrapCapabilityAndCliTests(RunSpecimenTestCase):
    def test_host_capabilities_selects_linux_bwrap_without_claiming_enforced(self) -> None:
        caps = host_capabilities()
        self.assertEqual(caps["default_backend"], "none")
        self.assertFalse(caps["backends"]["none"]["enforced"])
        bwrap = caps["backends"]["bwrap"]
        self.assertEqual(bwrap.get("platform"), "linux")
        self.assertIs(bwrap["available"], shutil.which("bwrap") is not None)
        self.assertNotIn("enforced", bwrap)
        blob = json.dumps(caps)
        self.assertIn("not an os sandbox", blob.lower())
        self.assertNotIn("is an OS sandbox", blob)

    def test_isolation_cli_reports_unavailable_without_failing(self) -> None:
        empty = self.ws.parent / f"no-bwrap-cli-{self.ws.name}"
        empty.mkdir()
        previous = os.environ.get("PATH", "")
        os.environ["PATH"] = str(empty)
        self.addCleanup(lambda: os.environ.__setitem__("PATH", previous))
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["isolation"])
        self.assertEqual(code, 0, stderr.getvalue())
        doc = json.loads(stdout.getvalue())
        self.assertFalse(doc["backends"]["bwrap"]["available"])


class BwrapConstructionNetworkTests(BwrapConstructionTests):
    def test_network_allowed_omits_unshare_net_and_records_allowed(self) -> None:
        tool, marker = self._plant_bwrap()
        path = write_contract(
            self.ws,
            "c.json",
            base_contract(isolation={"backend": "bwrap", "network": True}),
        )
        contract = load_contract(path)
        self.assertTrue(contract.isolation.network)
        plan = effective_plan(contract.isolation)
        self.assertEqual(plan["network"], "allowed")
        self.assertTrue(plan["enforced"])
        argv = confinement_argv(
            plan,
            [sys.executable, "work/job.py"],
            workspace=self.ws.resolve(),
            cwd=self.ws.resolve(),
            profile_path=self.ws / "isolation.sb",
        )
        self.assertFalse(marker.exists())
        self.assertNotIn("--unshare-net", argv)
        self.assertEqual(argv[0], str(tool.resolve()))

    def test_tool_inside_workspace_is_refused(self) -> None:
        from runspecimen.isolation import assert_tool_outside_workspace

        tool = self.ws / "bwrap"
        tool.write_text("#!/bin/sh\n", encoding="utf-8")
        tool.chmod(0o755)
        plan = {
            "backend": "bwrap",
            "enforced": True,
            "network": "denied",
            "tool": str(tool),
            "tool_sha256": sha256_file(tool),
        }
        with self.assertRaises(PreflightError) as ctx:
            assert_tool_outside_workspace(plan, self.ws)
        self.assertIn("inside the workspace", str(ctx.exception))


@unittest.skipUnless(
    shutil.which("bwrap"),
    "bwrap is not installed; real confinement spawn skipped",
)
class BwrapLinuxNetworkAndWriteTests(RunSpecimenTestCase):
    def test_network_is_denied_at_runtime(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        self.addCleanup(listener.close)

        job = textwrap.dedent(
            f"""\
            import socket
            import sys

            open("outputs/ran.txt", "w", encoding="utf-8").write("ran\\n")
            try:
                socket.create_connection(("127.0.0.1", {port}), timeout=1.0)
            except OSError as exc:
                print(f"network-denied errno={{exc.errno}}", flush=True)
                sys.exit(3)
            print("network-succeeded", flush=True)
            open("outputs/out.json", "w", encoding="utf-8").write('{{"status":"ok"}}\\n')
            sys.exit(0)
            """
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
        # Contract still requires out.json on success path; denied network exits 3.
        path = write_contract(self.ws, "c.json", base_contract(isolation={"backend": "bwrap"}))
        approve(self.ws, path)
        preflight(contract_path=path, workspace=self.ws)
        result = run_contract(contract_path=path, workspace=self.ws)
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        stdout = (state_dir / STDOUT_FILENAME).read_bytes()
        self.assertEqual(result["exit_code"], 3)
        self.assertIn(b"network-denied", stdout)
        self.assertNotIn(b"network-succeeded", stdout)
        self.assertIsNone(load_certificate(state_dir))
        for receipt in (load_approval(state_dir)["isolation"], load_state(state_dir)["isolation"]):
            _assert_enforced_bwrap_receipt(self, receipt)

    def test_workspace_write_still_succeeds_and_is_certified(self) -> None:
        job = textwrap.dedent(
            """\
            from pathlib import Path
            Path("outputs/ran.txt").write_text("payload-ran\\n", encoding="utf-8")
            Path("outputs/out.json").write_text('{"status":"ok"}\\n', encoding="utf-8")
            print("ok", flush=True)
            """
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
        path = write_contract(self.ws, "c.json", base_contract(isolation={"backend": "bwrap"}))
        approve(self.ws, path)
        preflight(contract_path=path, workspace=self.ws)
        result = run_contract(contract_path=path, workspace=self.ws)
        self.assertEqual(result["exit_code"], 0)
        postflight(contract_path=path, workspace=self.ws)
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        cert = load_certificate(state_dir)
        self.assertIsNotNone(cert)
        assert cert is not None
        _assert_enforced_bwrap_receipt(self, cert["isolation"])


if __name__ == "__main__":
    unittest.main()
