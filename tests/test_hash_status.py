"""Hashing, atomic writes, contract parsing, status/cli smoke tests."""

from __future__ import annotations

import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

from tests.helpers import SRC, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.cli import main
from runspecimen.contract import load_contract
from runspecimen.errors import ContractError, PreflightError, ProvenanceError
from runspecimen.hashutil import hash_source
from runspecimen.lease import hold_workspace_lease
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.status import status_for


class TestHashAtomic(RunSpecimenTestCase):
    def test_source_hash_deterministic_and_respects_excludes(self) -> None:
        (self.ws / "work" / "tmp").mkdir()
        (self.ws / "work" / "tmp" / "x.txt").write_text("ignored\n", encoding="utf-8")
        h1, m1 = hash_source(self.ws, ["work"], ["work/tmp"])
        h2, m2 = hash_source(self.ws, ["work"], ["work/tmp"])
        self.assertEqual(h1, h2)
        self.assertEqual(m1, m2)
        self.assertTrue(all(not e["path"].startswith("work/tmp/") for e in m1))

        (self.ws / "work" / "extra.txt").write_text("x\n", encoding="utf-8")
        h3, _ = hash_source(self.ws, ["work"], ["work/tmp"])
        self.assertNotEqual(h1, h3)

    def test_unexcluded_symlink_refused(self) -> None:
        target = self.ws / "work" / "real.txt"
        target.write_text("x\n", encoding="utf-8")
        link = self.ws / "work" / "link.txt"
        link.symlink_to(target)
        with self.assertRaises(ProvenanceError) as ctx:
            hash_source(self.ws, ["work"], [])
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_excluded_symlink_allowed(self) -> None:
        target = self.ws / "work" / "real.txt"
        target.write_text("x\n", encoding="utf-8")
        link = self.ws / "work" / "link.txt"
        link.symlink_to(target)
        hash_source(self.ws, ["work"], ["link.txt"])

    def test_atomic_write_json(self) -> None:
        path = self.ws / "state" / "s.json"
        atomic_write_json(path, {"a": 1, "b": 2})
        self.assertEqual(read_json(path), {"a": 1, "b": 2})

    def test_strict_bool_and_sha_hex(self) -> None:
        doc = base_contract()
        doc["postflight"]["require_outputs"] = 1
        cpath = write_contract(self.ws, "bad-bool.json", doc)
        with self.assertRaises(ContractError):
            load_contract(cpath)

        doc = base_contract()
        doc["postflight"]["source_unchanged"] = False
        cpath = write_contract(self.ws, "bad-prov.json", doc)
        with self.assertRaises(ContractError) as ctx:
            load_contract(cpath)
        self.assertIn("source_unchanged", str(ctx.exception))

        doc = base_contract()
        doc["postflight"]["output_sha256"] = {"outputs/out.json": "z" * 64}
        cpath = write_contract(self.ws, "bad-sha.json", doc)
        with self.assertRaises(ContractError) as ctx:
            load_contract(cpath)
        self.assertIn("hex", str(ctx.exception).lower())

        doc = base_contract(
            predecessor={
                "campaign_id": "camp",
                "run_id": "prior",
                "require_postflight": False,
                "refuse_if_failed": True,
            }
        )
        cpath = write_contract(self.ws, "bad-gate.json", doc)
        with self.assertRaises(ContractError) as ctx:
            load_contract(cpath)
        self.assertIn("mandatory-gating", str(ctx.exception))


class TestStatusCli(RunSpecimenTestCase):
    def test_doctor_and_validate_commands(self) -> None:
        from contextlib import redirect_stdout
        from io import StringIO

        cpath = write_contract(self.ws, "contract.json", base_contract())
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["doctor", "--workspace", str(self.ws)]), 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])

        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                main(["validate", "--workspace", str(self.ws), "--contract", str(cpath)]),
                0,
            )
        self.assertIn("runtime_id", out.getvalue())

    def test_approval_interrupt_is_clean(self) -> None:
        with patch("runspecimen.cli.approve_contract", side_effect=KeyboardInterrupt):
            self.assertEqual(
                main(
                    [
                        "approve",
                        "--workspace",
                        str(self.ws),
                        "--contract",
                        str(self.ws / "unused.json"),
                    ]
                ),
                130,
            )

    def test_status_and_cli_verify(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        postflight(contract_path=cpath, workspace=self.ws)

        doc = status_for(workspace=self.ws, campaign_id="camp", run_id="run-a")
        self.assertEqual(doc["phase"], "postflighted")
        self.assertTrue(doc["event_chain_ok"])

        from contextlib import redirect_stdout
        from io import StringIO

        buf = StringIO()
        with redirect_stdout(buf):
            rc = main(
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
        self.assertEqual(rc, 0)
        self.assertIn("certificate_id", buf.getvalue())

    def test_active_lease_blocks_preflight(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        with hold_workspace_lease(self.ws, holder="blocker"):
            with self.assertRaises(PreflightError) as ctx:
                preflight(contract_path=cpath, workspace=self.ws)
            self.assertIn("lease", str(ctx.exception).lower())

    def test_load_example_contract_shape(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "demo_contract.json"
        data = json.loads(example.read_text(encoding="utf-8"))
        cpath = write_contract(self.ws, "demo.json", data)
        contract = load_contract(cpath)
        self.assertEqual(contract.campaign_id, "demo-campaign")
        self.assertEqual(contract.version, 1)


if __name__ == "__main__":
    unittest.main()
