"""Schema versioning and golden legacy receipt tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import SRC, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.certificate import _recompute_certificate_id, build_certificate
from runspecimen.contract import load_contract
from runspecimen.errors import CertificateError, ContractError
from runspecimen.schema import (
    CURRENT_RECEIPT_SCHEMA_VERSION,
    assert_supported_contract_version,
    assert_supported_receipt_schema,
    certificate_id_material,
)

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_CERT = (
    ROOT
    / "examples"
    / "showcase"
    / ".runspecimen"
    / "runs"
    / "showcase-campaign"
    / "run-001"
    / "certificate.json"
)


class TestSchemaVersions(unittest.TestCase):
    def test_unknown_contract_version_fails_closed(self) -> None:
        with self.assertRaises(ContractError) as ctx:
            assert_supported_contract_version(99)
        self.assertIn("unsupported contract version: 99", str(ctx.exception))
        self.assertIn("SCHEMA_COMPATIBILITY", str(ctx.exception))

    def test_parse_rejects_unknown_contract_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_contract(Path(tmp), "bad.json", base_contract(version=2))
            with self.assertRaises(ContractError) as ctx:
                load_contract(path)
            self.assertIn("unsupported contract version: 2", str(ctx.exception))

    def test_unknown_receipt_schema_fails_closed(self) -> None:
        with self.assertRaises(CertificateError) as ctx:
            assert_supported_receipt_schema({"schema_version": 99})
        msg = str(ctx.exception)
        self.assertIn("unsupported receipt schema_version: 99", msg)
        self.assertIn("SCHEMA_COMPATIBILITY", msg)

    def test_non_integer_receipt_schema_fails_closed(self) -> None:
        with self.assertRaises(CertificateError):
            assert_supported_receipt_schema({"schema_version": "1"})

    def test_absent_schema_version_is_legacy_v1(self) -> None:
        self.assertEqual(assert_supported_receipt_schema({}), 1)

    def test_new_certificate_emits_schema_version_bound_into_id(self) -> None:
        class _C:
            campaign_id = "camp"
            run_id = "run"
            contract_hash = "a" * 64

        cert = build_certificate(
            contract=_C(),  # type: ignore[arg-type]
            state={"exit_code": 0, "run_result": "completed"},
            source_hash="b" * 64,
            output_digests={"out.json": "c" * 64},
            event_head="d" * 64,
            approval={"expires_at_unix": 1},
            runtime={"runtime_id": "e" * 64},
        )
        self.assertEqual(cert["schema_version"], CURRENT_RECEIPT_SCHEMA_VERSION)
        self.assertIn("schema_version", certificate_id_material(cert))
        self.assertEqual(_recompute_certificate_id(cert), cert["certificate_id"])


class TestGoldenLegacyReceipt(unittest.TestCase):
    def test_showcase_certificate_is_legacy_v1_and_self_consistent(self) -> None:
        self.assertTrue(SHOWCASE_CERT.is_file(), "showcase certificate fixture missing")
        cert = json.loads(SHOWCASE_CERT.read_text(encoding="utf-8"))
        self.assertNotIn("schema_version", cert)
        self.assertEqual(assert_supported_receipt_schema(cert), 1)
        self.assertEqual(_recompute_certificate_id(cert), cert["certificate_id"])
        self.assertNotIn("schema_version", certificate_id_material(cert))
