"""Adversarial / deny-by-default coverage for contract parsing."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.contract import (  # noqa: E402
    MAX_ARGV_LEN,
    MAX_CONTRACT_BYTES,
    MAX_STRING_CHARS,
    check_contract_paths,
    load_contract,
    parse_contract,
)
from runspecimen.errors import ContractError, PathEscapeError  # noqa: E402
from tests.helpers import PYTHON, base_contract, write_contract  # noqa: E402


class ContractParserAdversarialTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="rs-adv-")
        self.ws = Path(self._td.name)
        (self.ws / "work").mkdir()
        (self.ws / "outputs").mkdir()
        (self.ws / "work" / "job.py").write_text("print('x')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write(self, doc) -> Path:
        return write_contract(self.ws, "c.json", doc)

    def test_malformed_json_truncated(self) -> None:
        path = self.ws / "bad.json"
        path.write_text('{"version": 1', encoding="utf-8")
        with self.assertRaises(ContractError):
            load_contract(path)

    def test_malformed_json_empty_and_non_object(self) -> None:
        empty = self.ws / "empty.json"
        empty.write_text("", encoding="utf-8")
        with self.assertRaises(ContractError):
            load_contract(empty)
        arr = self.ws / "arr.json"
        arr.write_text("[1,2,3]\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            load_contract(arr)

    def test_bad_utf8_and_bom(self) -> None:
        bad = self.ws / "badutf.json"
        bad.write_bytes(b"\xff\xfe{\"version\":1}")
        with self.assertRaises(ContractError):
            load_contract(bad)

    def test_duplicate_keys_rejected(self) -> None:
        path = self.ws / "dup.json"
        path.write_text('{"version":1,"version":2,"campaign_id":"c","run_id":"r"}\n', encoding="utf-8")
        with self.assertRaises(ContractError) as ctx:
            load_contract(path)
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_unknown_fields_on_nested_objects(self) -> None:
        for overrides in (
            {"runtime": {"env_allowlist": [], "extra": True}},
            {"isolation": {"backend": "none", "weird": 1}},
            {"postflight": {**base_contract()["postflight"], "bonus": 1}},
            {"source": {"roots": ["work"], "excludes": [], "oops": True}},
            {"predecessor": {"campaign_id": "camp", "run_id": "prev", "x": 1}},
        ):
            doc = base_contract(**overrides)
            path = self._write(doc)
            with self.assertRaises(ContractError):
                load_contract(path)

    def test_bool_is_not_int_and_float_version(self) -> None:
        doc = base_contract()
        doc["caps"]["wall_timeout_sec"] = True
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))
        doc = base_contract()
        doc["version"] = 1.0
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))

    def test_empty_argv_and_ids(self) -> None:
        doc = base_contract(argv=[])
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))
        doc = base_contract(campaign_id="")
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))

    def test_source_unchanged_must_be_true(self) -> None:
        doc = base_contract()
        doc["postflight"]["source_unchanged"] = False
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))

    def test_predecessor_gating_flags(self) -> None:
        doc = base_contract(
            predecessor={
                "campaign_id": "camp",
                "run_id": "prev",
                "require_postflight": False,
                "refuse_if_failed": True,
            }
        )
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))

    def test_cap_and_ttl_extrema(self) -> None:
        doc = base_contract()
        doc["caps"]["wall_timeout_sec"] = 0
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))
        doc = base_contract()
        doc["approval"]["ttl_sec"] = 0
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))

    def test_sha256_length_and_hex(self) -> None:
        doc = base_contract()
        doc["postflight"]["output_sha256"] = {"outputs/out.json": "abcd"}
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))
        doc = base_contract()
        doc["postflight"]["output_sha256"] = {"outputs/out.json": "g" * 64}
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))

    def test_path_escape_on_check_contract_paths(self) -> None:
        doc = base_contract(cwd="../outside")
        contract = load_contract(self._write(doc))
        with self.assertRaises(PathEscapeError):
            check_contract_paths(contract, self.ws)

    def test_policy_abs_and_tilde_refused(self) -> None:
        digest = "a" * 64
        for path in ("/etc/passwd", "~/secret"):
            doc = base_contract(policy={"id": "p1", "path": path, "sha256": digest})
            with self.assertRaises(ContractError):
                load_contract(self._write(doc))

    def test_unsafe_campaign_and_run_ids(self) -> None:
        for bad in ("../x", "has space", "slash/id", ".hidden"):
            doc = base_contract(campaign_id=bad)
            with self.assertRaises(ContractError):
                load_contract(self._write(doc))
            doc = base_contract(run_id=bad)
            with self.assertRaises(ContractError):
                load_contract(self._write(doc))

    def test_nul_in_string_rejected(self) -> None:
        path = self.ws / "nul.json"
        doc = base_contract()
        raw = json.dumps(doc)
        raw = raw.replace('"cwd": "."', '"cwd": ".\u0000"')
        path.write_text(raw + "\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            load_contract(path)

    def test_oversized_string_and_argv(self) -> None:
        doc = base_contract(cwd="x" * (MAX_STRING_CHARS + 1))
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))
        doc = base_contract(argv=[PYTHON] + ["a"] * MAX_ARGV_LEN)  # 1 + MAX
        with self.assertRaises(ContractError):
            load_contract(self._write(doc))

    def test_oversized_contract_bytes(self) -> None:
        path = self.ws / "huge.json"
        # Build a valid-looking object but oversized via padding field unknown → unknown field
        # Prefer size gate before schema: write huge bytes.
        path.write_bytes(b"{" + b" " * (MAX_CONTRACT_BYTES + 10) + b"}")
        with self.assertRaises(ContractError) as ctx:
            load_contract(path)
        self.assertIn("max size", str(ctx.exception))

    def test_happy_path_still_loads(self) -> None:
        contract = load_contract(self._write(base_contract()))
        self.assertEqual(contract.campaign_id, "camp")
        check_contract_paths(contract, self.ws)


if __name__ == "__main__":
    unittest.main()
