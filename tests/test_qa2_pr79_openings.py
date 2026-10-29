"""QA2 remaining-head regressions that must run on Linux CI.

These assert the iOS UI-gate harness, launch-fault smoke labeling, approval
display escaping, and the committed CI census. They do not raise any wait.
"""

from __future__ import annotations

import re
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class QA2PR79OpeningsTests(unittest.TestCase):
    def test_test_action_does_not_wait_for_debugger(self) -> None:
        spec = yaml.safe_load(_read("apps/ios/project.yml"))
        test = spec["schemes"]["RunSpecimenObserve"]["test"]
        self.assertIs(test.get("debugEnabled"), False)

    def test_test_action_disables_main_thread_checker_and_activity_mode(self) -> None:
        spec = yaml.safe_load(_read("apps/ios/project.yml"))
        test = spec["schemes"]["RunSpecimenObserve"]["test"]
        self.assertIs(test.get("disableMainThreadChecker"), True)
        env = test.get("environmentVariables") or {}
        mode = env.get("OS_ACTIVITY_DT_MODE")
        if isinstance(mode, dict):
            mode = mode.get("value")
        self.assertIn(str(mode).upper(), {"NO", "0", "FALSE"})

    def test_recovery_copy_query_is_scoped_to_activity_list(self) -> None:
        source = _read("apps/ios/Tests/ObserveRecoveryUITests/RecoveryUITests.swift")
        self.assertNotIn('descendants(matching: .any)["Copy"]', source)
        self.assertRegex(
            source,
            r'otherElements\["ActivityListView"\]\.buttons\["Copy"\]',
        )
        waits = [int(match) for match in re.findall(r"waitForExistence\(timeout:\s*(\d+)", source)]
        self.assertTrue(waits)
        self.assertLessEqual(max(waits), 90)
        self.assertIn("timeout: 90", source)

    def test_recovery_teardown_dismisses_sheet_and_terminates(self) -> None:
        source = _read("apps/ios/Tests/ObserveRecoveryUITests/RecoveryUITests.swift")
        self.assertIn("override func tearDown()", source)
        self.assertIn('otherElements["PopoverDismissRegion"]', source)
        self.assertIn("app.terminate()", source)

    def test_ios_script_captures_failure_diagnostics(self) -> None:
        script = _read("apps/ios/Scripts/test_ios_observe.sh")
        workflow = _read(".github/workflows/ci.yml")
        self.assertIn("failure-diagnostics", script)
        self.assertIn("log show", script)
        self.assertIn("launchctl list", script)
        self.assertRegex(script, r"uptime|vm_stat")
        self.assertIn("failure-diagnostics", workflow)

    def test_launch_fault_workflow_labels_load_as_smoke(self) -> None:
        workflow = _read(".github/workflows/launch-fault-stress.yml")
        self.assertRegex(workflow, r"(?i)smoke")
        self.assertIn("python -m unittest tests.test_launch_faults", workflow)
        self.assertNotRegex(
            workflow,
            r"python -m unittest tests\.test_launch_faults.*\|\|\s*true",
        )

    def test_approval_review_text_is_escaped_not_raw(self) -> None:
        package = _read("apps/macos/Sources/RunSpecimenCore/RSBA2Package.swift")
        session = _read("apps/ios/Sources/RunSpecimenObserve/Services/CompanionSession.swift")
        self.assertIn("public static func displayText", package)
        self.assertIn("Nonce: \\(displayText(fields.nonce))", package)
        self.assertIn("nonce \\(RSBA2Package.displayText(nonce))", session)
        self.assertIn(".format", package)
        self.assertIn(".control", package)

    def test_qa_census_discloses_seventeen_ios_failures(self) -> None:
        census = _read("docs/QA2_CI_CENSUS_2026-10-27.md")
        summary = yaml.safe_load(_read("evidence/QA2-ci-census-summary.json"))
        rows = _read("evidence/QA2-ios-observe-tests-all-attempts.tsv").splitlines()[1:]
        failures = [row for row in rows if "\tfailure\t" in row]
        self.assertIn("17 failures", census)
        self.assertEqual(summary["outcomes"]["failure"], 17)
        self.assertEqual(len(failures), 17)

    def test_recovery_export_content_is_unit_tested(self) -> None:
        tests = _read("apps/ios/Tests/ObserveSchemaTests/SchemaTests.swift")
        self.assertIn("rotationRecoveryDiagnostics.contains", tests)
        self.assertIn("Recovery evidence is retained", tests)
