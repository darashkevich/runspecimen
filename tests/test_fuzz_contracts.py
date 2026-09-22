"""Stdlib mutation tests for fail-closed parsing, paths, and terminal phases.

No extra fuzzer dependency. A mutation may parse or raise ContractError /
PathEscapeError. Any other exception fails the test.
"""

from __future__ import annotations

import copy
import random
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from tests.helpers import SRC, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.contract import check_contract_paths, load_contract
from runspecimen.errors import ContractError, PathEscapeError, PreflightError
from runspecimen.paths import run_state_dir
from runspecimen.preflight import preflight


_FAIL_CLOSED = (ContractError, PathEscapeError)


class FuzzContractTests(unittest.TestCase):
    def test_random_contract_mutations_fail_closed(self) -> None:
        rng = random.Random(20260922)
        with self._workspace() as workspace:
            for i in range(200):
                doc = self._mutate(rng, copy.deepcopy(base_contract()))
                path = write_contract(workspace, f"fuzz-{i}.json", doc)
                try:
                    load_contract(path)
                except ContractError:
                    continue
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"mutation {i} raised {type(exc).__name__}: {exc}")

    def test_path_mutations_fail_closed(self) -> None:
        escapes = [
            "../outside",
            "/etc/passwd",
            "work/../../outside",
            "outputs/../../.ssh/id_rsa",
            "//etc/passwd",
        ]
        with self._workspace() as workspace:
            for rel in escapes:
                doc = base_contract()
                doc["cwd"] = rel
                path = write_contract(workspace, "escape.json", doc)
                contract = load_contract(path)
                with self.assertRaises(_FAIL_CLOSED):
                    check_contract_paths(contract, workspace)

    def test_terminal_phases_refuse_reentry(self) -> None:
        from runspecimen.state import update_state
        from tests.helpers import approve

        with self._workspace() as workspace:
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()
            (workspace / "work" / "job.py").write_text("print('ok')\n", encoding="utf-8")
            path = write_contract(workspace, "contract.json", base_contract())
            approve(workspace, path)
            contract = load_contract(path)
            state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
            for phase in ("running", "completed", "failed", "postflighted", "abandoned"):
                update_state(state_dir, phase=phase)
                with self.assertRaises(PreflightError) as ctx:
                    preflight(contract_path=path, workspace=workspace)
                self.assertIn(phase, str(ctx.exception))

    def _mutate(self, rng: random.Random, doc: dict) -> dict:
        roll = rng.randrange(6)
        if roll == 0:
            doc["version"] = rng.choice([0, 2, 99, True, "1", None])
        elif roll == 1:
            doc[f"extra_{rng.randrange(1000)}"] = rng.choice([1, "x", True, None, []])
        elif roll == 2:
            doc["argv"] = rng.choice([[], [""], "python3", None, [1]])
        elif roll == 3:
            doc["cwd"] = rng.choice(["../x", "/tmp", 1, None])
        elif roll == 4:
            doc["isolation"] = rng.choice(
                [
                    {"backend": "none", "network": True},
                    {"backend": "seatbelt"},
                    {"backend": "sandbox-exec", "extra": True},
                    "none",
                ]
            )
        else:
            doc.pop(rng.choice(["campaign_id", "postflight", "caps", "source"]), None)
        return doc

    @contextmanager
    def _workspace(self):
        with tempfile.TemporaryDirectory(prefix="runspecimen-fuzz-") as raw:
            yield Path(raw)


class GoldenReceiptTests(unittest.TestCase):
    def test_optional_receipt_fields_change_certificate_id(self) -> None:
        from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
        from runspecimen.schema import certificate_id_material

        body = {
            "approval_expires_at_unix": 1,
            "campaign_id": "camp",
            "contract_hash": "ab" * 32,
            "event_head": "cd" * 32,
            "exit_code": 0,
            "issued_at": "2026-09-22T00:00:00Z",
            "output_digests": {},
            "run_id": "run-a",
            "run_result": "ok",
            "runtime": {"runtime_id": "rt"},
            "schema_version": 1,
            "source_hash": "ef" * 32,
        }
        plain = sha256_bytes(canonical_json_bytes(certificate_id_material(body)))
        with_isolation = dict(body)
        with_isolation["isolation"] = {
            "backend": "none",
            "enforced": False,
            "network": "not-enforced",
        }
        bound = sha256_bytes(canonical_json_bytes(certificate_id_material(with_isolation)))
        self.assertNotEqual(plain, bound)
        self.assertNotIn("isolation", certificate_id_material(body))
        self.assertEqual(
            certificate_id_material(with_isolation)["isolation"]["backend"],
            "none",
        )


if __name__ == "__main__":
    unittest.main()
