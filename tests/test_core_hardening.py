"""Regression coverage for exact contract and source provenance."""

from __future__ import annotations

import json
from unittest.mock import patch

from tests.helpers import RunSpecimenTestCase, approve, base_contract, write_contract
from runspecimen.approve import approval_is_valid
from runspecimen.contract import load_contract, parse_contract
from runspecimen.errors import ContractError, PostflightError, PreflightError, ProvenanceError
from runspecimen.hashutil import hash_source, sha256_bytes
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.runtime import runtime_provenance


class TestContractSnapshot(RunSpecimenTestCase):
    def test_contract_hash_describes_the_bytes_that_were_parsed(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        original = cpath.read_bytes()

        def replace_before_validation(data, **kwargs):
            replacement = base_contract(argv=["different-command"])
            write_contract(self.ws, "contract.json", replacement)
            return parse_contract(data, **kwargs)

        with patch("runspecimen.contract.parse_contract", side_effect=replace_before_validation):
            contract = load_contract(cpath)
        self.assertEqual(contract.argv, tuple(base_contract()["argv"]))
        self.assertEqual(contract.contract_hash, sha256_bytes(original))
        self.assertNotEqual(contract.contract_hash, sha256_bytes(cpath.read_bytes()))

    def test_missing_equals_is_not_silently_treated_as_null(self) -> None:
        doc = base_contract()
        del doc["postflight"]["json_equals"][0]["equals"]
        cpath = write_contract(self.ws, "contract.json", doc)
        with self.assertRaisesRegex(ContractError, "equals is required"):
            load_contract(cpath)


class TestSourceRootSymlinks(RunSpecimenTestCase):
    def test_symlink_used_as_a_source_root_is_refused(self) -> None:
        (self.ws / "alias").symlink_to(self.ws / "work", target_is_directory=True)
        with self.assertRaisesRegex(ProvenanceError, "symlink"):
            hash_source(self.ws, ["alias"], [])

    def test_symlink_in_source_root_parent_is_refused(self) -> None:
        (self.ws / "alias").symlink_to(self.ws / "work", target_is_directory=True)
        with self.assertRaisesRegex(ProvenanceError, "symlink"):
            hash_source(self.ws, ["alias/job.py"], [])

    def test_explicitly_excluded_symlink_root_is_skipped(self) -> None:
        (self.ws / "alias").symlink_to(self.ws / "work", target_is_directory=True)
        digest, manifest = hash_source(self.ws, ["work", "alias"], ["alias"])
        expected, expected_manifest = hash_source(self.ws, ["work"], [])
        self.assertEqual(digest, expected)
        self.assertEqual(manifest, expected_manifest)


class TestApprovalDeadline(RunSpecimenTestCase):
    def test_approval_expiring_during_runtime_checks_cannot_launch(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract(approval={"ttl_sec": 1}))
        approve(self.ws, cpath, now=1000)

        for module, operation in (("run", run_contract), ("preflight", preflight)):
            with self.subTest(operation=module):
                with patch(f"runspecimen.{module}.time.time", return_value=1000) as clock:
                    def runtime_takes_time(contract, workspace):
                        result = runtime_provenance(contract, workspace)
                        clock.return_value = 1002
                        return result

                    with patch(f"runspecimen.{module}.runtime_provenance", side_effect=runtime_takes_time):
                        with patch("runspecimen.run.subprocess.Popen") as spawn:
                            with self.assertRaisesRegex(PreflightError, "expired"):
                                operation(contract_path=cpath, workspace=self.ws)
                            spawn.assert_not_called()

    def test_expiry_boundary_and_nonfinite_timestamps_fail_closed(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approval = approve(self.ws, cpath, now=1000)
        contract = load_contract(cpath)
        source = approval["source_hash"]
        valid, reason = approval_is_valid(approval, contract, source, now=4600)
        self.assertFalse(valid)
        self.assertIn("expired", reason)
        for expires in (True, float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(expires=expires):
                approval["expires_at_unix"] = expires
                valid, reason = approval_is_valid(approval, contract, source, now=1000)
                self.assertFalse(valid)
                self.assertIn("invalid", reason)


class TestJsonAssertions(RunSpecimenTestCase):
    def test_json_booleans_do_not_satisfy_numeric_assertions(self) -> None:
        for index, (actual, expected) in enumerate((
            (True, 1), (False, 0), ({"nested": [True]}, {"nested": [1]})
        )):
            with self.subTest(actual=actual, expected=expected):
                output = f"outputs/assertion-{index}.json"
                payload = json.dumps({"result": actual})
                (self.ws / "work" / "job.py").write_text(
                    "from pathlib import Path\n"
                    f"Path({output!r}).write_text({payload!r})\n",
                    encoding="utf-8",
                )
                doc = base_contract(run_id=f"assertion-{index}", outputs={"required": [output]})
                doc["postflight"]["json_equals"] = [
                    {"path": output, "field": "result", "equals": expected}
                ]
                cpath = write_contract(self.ws, f"assertion-{index}.json", doc)
                approve(self.ws, cpath)
                run_contract(contract_path=cpath, workspace=self.ws)
                with self.assertRaisesRegex(PostflightError, "json_equals"):
                    postflight(contract_path=cpath, workspace=self.ws)
