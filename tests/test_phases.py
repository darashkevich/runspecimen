"""Opt-in isolation, shared policy, retain, templates, and the first-run lease."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

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
from runspecimen.bundle import retain_incident_bundle
from runspecimen.certificate import load_certificate
from runspecimen.cli import main
from runspecimen.contract import load_contract
from runspecimen.errors import ContractError, LeaseError, PreflightError, RunSpecimenError
from runspecimen.isolation import confinement_argv, effective_plan, host_capabilities
from runspecimen.lease import Lease
from runspecimen.paths import run_state_dir
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract

ROOT = Path(__file__).resolve().parents[1]


class IsolationContractTests(unittest.TestCase):
    def test_absent_isolation_is_unconfined(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            path = write_contract(workspace, "c.json", base_contract())
            contract = load_contract(path)
            self.assertEqual(contract.isolation.backend, "none")
            self.assertFalse(contract.isolation.network)
            plan = effective_plan(contract.isolation)
            self.assertFalse(plan["enforced"])
            self.assertEqual(plan["network"], "not-enforced")
            wrapped = confinement_argv(
                plan,
                ["python3", "work/job.py"],
                workspace=workspace,
                cwd=workspace,
                profile_path=workspace / "isolation.sb",
            )
            self.assertEqual(wrapped, ["python3", "work/job.py"])
            self.assertFalse((workspace / "isolation.sb").exists())

    def test_network_with_none_is_rejected(self) -> None:
        doc = base_contract(isolation={"backend": "none", "network": True})
        with tempfile.TemporaryDirectory() as raw:
            path = write_contract(Path(raw), "c.json", doc)
            with self.assertRaises(ContractError) as ctx:
                load_contract(path)
            self.assertIn("does not confine the network", str(ctx.exception))

    def test_bwrap_wraps_argv_without_executing(self) -> None:
        from unittest.mock import patch

        from runspecimen.contract import IsolationSpec
        from runspecimen.isolation import confinement_argv, effective_plan

        spec = IsolationSpec(backend="bwrap", network=False)
        with tempfile.TemporaryDirectory() as raw:
            tool = Path(raw) / "bwrap"
            tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            tool.chmod(0o755)
            with patch("runspecimen.isolation.discover_tool", return_value=str(tool)):
                plan = effective_plan(spec)
            self.assertTrue(plan["enforced"])
            self.assertEqual(plan["network"], "denied")
            self.assertEqual(len(plan["tool_sha256"]), 64)
            argv = confinement_argv(
                plan,
                ["/usr/bin/python3", "work/job.py"],
                workspace=Path("/work"),
                cwd=Path("/work"),
                profile_path=Path("/work/isolation.sb"),
            )
            self.assertEqual(argv[0], plan["tool"])
            self.assertIn("--unshare-net", argv)
            self.assertIn("--", argv)
            self.assertEqual(argv[-2:], ["/usr/bin/python3", "work/job.py"])
            self.assertNotIn("shell", argv)

    def test_missing_declared_backend_fails_closed(self) -> None:
        doc = base_contract(isolation={"backend": "bwrap"})
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()
            (workspace / "work" / "job.py").write_text("print('ok')\n", encoding="utf-8")
            path = write_contract(workspace, "c.json", doc)
            if shutil.which("bwrap"):
                self.skipTest("bwrap is installed; missing-backend case is not this host")
            with self.assertRaises(PreflightError) as ctx:
                approve(workspace, path)
            self.assertIn("not available", str(ctx.exception))

    def test_default_run_records_unconfined_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()
            (workspace / "work" / "job.py").write_text(
                "import json\nfrom pathlib import Path\n"
                "Path('outputs/out.json').write_text(json.dumps({'status':'ok'})+'\\n')\n",
                encoding="utf-8",
            )
            path = write_contract(workspace, "c.json", base_contract())
            approve(workspace, path)
            approval = load_approval(run_state_dir(workspace, "camp", "run-a"))
            self.assertEqual(approval["approver"]["kind"], "local_os_user")
            self.assertTrue(approval["approver"]["user"])
            self.assertEqual(approval["isolation"]["backend"], "none")
            self.assertNotIn("policy", approval)
            preflight(contract_path=path, workspace=workspace)
            run_contract(contract_path=path, workspace=workspace)
            postflight(contract_path=path, workspace=workspace)
            cert = load_certificate(run_state_dir(workspace, "camp", "run-a"))
            self.assertEqual(cert["isolation"]["backend"], "none")
            self.assertFalse(cert["isolation"]["enforced"])
            self.assertEqual(cert["approver"]["kind"], "local_os_user")
            self.assertNotIn("policy", cert)
            self.assertFalse((run_state_dir(workspace, "camp", "run-a") / "isolation.sb").exists())


@unittest.skipUnless(shutil.which("sandbox-exec"), "sandbox-exec is not installed")
class SeatbeltIntegrationTests(RunSpecimenTestCase):
    def test_write_outside_workspace_fails(self) -> None:
        job = textwrap.dedent(
            """\
            import pathlib, sys
            pathlib.Path("outputs/out.json").write_text('{"status":"ok"}\\n')
            try:
                pathlib.Path("/tmp/runspecimen-isolation-escape").write_text("nope")
            except OSError:
                sys.exit(0)
            sys.exit(2)
            """
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
        doc = base_contract(isolation={"backend": "sandbox-exec", "network": False})
        path = write_contract(self.ws, "c.json", doc)
        approve(self.ws, path)
        preflight(contract_path=path, workspace=self.ws)
        result = run_contract(contract_path=path, workspace=self.ws)
        self.assertEqual(result["exit_code"], 0, result)
        postflight(contract_path=path, workspace=self.ws)
        cert = load_certificate(run_state_dir(self.ws, "camp", "run-a"))
        self.assertEqual(cert["isolation"]["backend"], "sandbox-exec")
        self.assertTrue(cert["isolation"]["enforced"])
        self.assertEqual(cert["isolation"]["network"], "denied")
        self.assertIn("Not an OS sandbox", cert["isolation"]["residual"])
        self.assertFalse(Path("/tmp/runspecimen-isolation-escape").exists())


class PolicyAndRetainTests(RunSpecimenTestCase):
    def test_policy_ceiling_and_receipt(self) -> None:
        policy = {
            "version": 1,
            "id": "research-default",
            "max_wall_timeout_sec": 30,
            "argv0_allow": [sys.executable],
            "require_isolation_backend": "none",
        }
        blob = (json.dumps(policy, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (self.ws / "policy.json").write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        doc = base_contract(
            policy={"id": "research-default", "path": "policy.json", "sha256": digest},
            argv=[sys.executable, "work/job.py"],
        )
        path = write_contract(self.ws, "c.json", doc)
        approve(self.ws, path)
        preflight(contract_path=path, workspace=self.ws)
        run_contract(contract_path=path, workspace=self.ws)
        postflight(contract_path=path, workspace=self.ws)
        cert = load_certificate(run_state_dir(self.ws, "camp", "run-a"))
        self.assertEqual(cert["policy"]["sha256"], digest)
        self.assertEqual(cert["policy"]["id"], "research-default")

        too_wide = base_contract(
            run_id="run-b",
            policy={"id": "research-default", "path": "policy.json", "sha256": digest},
            caps={
                "wall_timeout_sec": 31,
                "stdout_max_bytes": 65536,
                "stderr_max_bytes": 65536,
            },
        )
        wide_path = write_contract(self.ws, "wide.json", too_wide)
        with self.assertRaises(PreflightError) as ctx:
            approve(self.ws, wide_path)
        self.assertIn("exceeds shared policy", str(ctx.exception))

    def test_retain_refuses_workspace_and_copies_outside(self) -> None:
        path = write_contract(self.ws, "c.json", base_contract())
        approve(self.ws, path)
        inside = self.ws / "pack"
        with self.assertRaises(RunSpecimenError):
            retain_incident_bundle(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                out_dir=inside,
            )
        with tempfile.TemporaryDirectory(prefix="runspecimen-retain-") as raw:
            dest = Path(raw) / "pack"
            manifest = retain_incident_bundle(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                out_dir=dest,
            )
            self.assertEqual(manifest["kind"], "retained_incident_bundle")
            self.assertEqual(manifest["retention"], "local_directory")
            self.assertTrue((dest / "approval.json").is_file())
            self.assertTrue((dest / "manifest.json").is_file())


class DistributionArtifactTests(unittest.TestCase):
    def test_templates_parse(self) -> None:
        root = ROOT / "examples" / "templates"
        for rel in (
            "research/contract.json",
            "ml-eval/contract.json",
            "security/contract.json",
            "../campaigns/adversarial-first-run/contract.json",
        ):
            load_contract((root / rel).resolve())

    def test_security_template_policy_hash_matches_file(self) -> None:
        policy = ROOT / "examples" / "templates" / "shared-policy" / "policy.json"
        contract = load_contract(ROOT / "examples" / "templates" / "security" / "contract.json")
        self.assertEqual(contract.policy.sha256, hashlib.sha256(policy.read_bytes()).hexdigest())
        self.assertEqual(contract.isolation.backend, "none")

    def test_homebrew_formula_pins_published_sdist(self) -> None:
        text = (ROOT / "packaging" / "homebrew" / "runspecimen.rb").read_text(encoding="utf-8")
        identity = (ROOT / "docs" / "RELEASE_IDENTITY.md").read_text(encoding="utf-8")
        self.assertIn(
            "https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.14/runspecimen-0.2.0rc14.tar.gz",
            text,
        )
        self.assertIn("6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3", text)
        self.assertIn("6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3", identity)
        self.assertIn('assert_match "0.2.0rc14"', text)
        self.assertIn("0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5", identity)
        self.assertNotIn("unreleased", text.lower())

    def test_isolation_cli(self) -> None:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["isolation"]), 0)
        self.assertIn('"default_backend": "none"', buf.getvalue())
        caps = host_capabilities()
        self.assertEqual(caps["default_backend"], "none")
        self.assertIn("not an OS sandbox", caps["claim"])


class FirstRunLeaseTests(unittest.TestCase):
    def test_second_worker_is_refused(self) -> None:
        script = textwrap.dedent(
            """\
            import sys, time
            from pathlib import Path
            sys.path.insert(0, sys.argv[1])
            from runspecimen.lease import hold_workspace_lease
            marker = Path(sys.argv[3])
            with hold_workspace_lease(Path(sys.argv[2]), holder="first-run"):
                marker.write_text("held")
                time.sleep(30)
            """
        )
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            marker = workspace / "held"
            proc = subprocess.Popen(
                [sys.executable, "-c", script, str(SRC), str(workspace), str(marker)],
            )
            try:
                deadline = time.time() + 10
                while time.time() < deadline and not marker.exists():
                    if proc.poll() is not None:
                        self.fail(f"lease holder exited early: {proc.returncode}")
                    time.sleep(0.05)
                self.assertTrue(marker.exists())
                with self.assertRaises(LeaseError):
                    Lease.for_workspace(workspace, holder="second-run").acquire()
            finally:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
