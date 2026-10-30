"""PR76-specific QA2 regressions that must run on Linux CI."""

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class QA2PR76OpeningsTests(unittest.TestCase):
    def test_transport_errors_map_to_unknown_settlement(self) -> None:
        session = _read("apps/ios/Sources/RunSpecimenObserve/Services/CompanionSession.swift")
        tests = _read("apps/ios/Tests/ObserveSchemaTests/SettlementOutcomeRegressionTests.swift")
        self.assertIn("unknownSettlementMessage", session)
        self.assertIn("settlementUnknown", session)
        self.assertIn("URLError(.timedOut)", tests)
        self.assertIn("URLError(.networkConnectionLost)", tests)
        self.assertIn("http(502", tests)
        self.assertIn("garbage 200 body", tests)

    def test_mac_symbol_scan_is_committed_and_reports_disk_space(self) -> None:
        scanner = _read("apps/macos/Scripts/scan_required_reason_apis.py")
        disposition = _read("evidence/PRIVACY-DISPOSITION.md")
        evidence = ROOT / "evidence/QA2-current-mac-symbol-scan.json"
        self.assertTrue(evidence.is_file())
        self.assertIn("undeclared_categories", scanner)
        self.assertIn("scan_required_reason_apis.py", disposition)
        self.assertIn("DiskSpace", evidence.read_text(encoding="utf-8"))

    def test_enrollment_success_does_not_publish_into_successor_pairing(self) -> None:
        session = _read("apps/ios/Sources/RunSpecimenObserve/Services/CompanionSession.swift")
        tests = _read("apps/ios/Tests/ObserveSchemaTests/SchemaTests.swift")
        self.assertIn("guard originatingPairing == pairingRevision", session)
        self.assertIn("successorPairing: true", tests)
        self.assertIn("successor sentinel", tests)

    def test_re_pair_success_resynchronizes_trust_draft_baselines(self) -> None:
        view = _read("apps/ios/Sources/RunSpecimenObserve/Views/PairingView.swift")
        tests = _read("apps/ios/Tests/ObserveSchemaTests/SettlementOutcomeRegressionTests.swift")
        self.assertIn("trustDraft.synchronize(macKey: session.macSessionPublicKey, holderID: session.pinnedHolderId)", view)
        self.assertIn("testQA2ReenteringSamePinsAfterRePairIsADeliberateEdit", tests)

    def test_clipboard_and_refresh_ui_tests_terminate_the_app(self) -> None:
        clipboard = _read("apps/ios/Tests/ObserveRecoveryUITests/RecoveryClipboardUITests.swift")
        refresh = _read("apps/ios/Tests/ObserveRecoveryUITests/RefreshUITests.swift")
        self.assertIn("override func tearDown()", clipboard)
        self.assertIn("app.terminate()", clipboard)
        self.assertIn("override func tearDown()", refresh)
        self.assertIn("app.terminate()", refresh)

    def test_ios_privacy_gate_rejects_objc_required_reason_constants(self) -> None:
        gate = _read("apps/ios/Scripts/ios_privacy_gate.py")
        tests = _read("tests/test_ios_privacy_gate.py")
        self.assertIn("_NSFileModificationDate", gate)
        self.assertIn("AvailableCapacity(?:ForImportantUsage", gate)
        self.assertIn("unreviewed required-reason code", gate)
        self.assertIn("test_qa2_objc_imports_and_unknown_reason_are_rejected", tests)
