"""QA2 remaining-head regressions that must run on Linux CI.

These assert the iOS UI-gate harness, launch-fault smoke labeling, approval
display escaping, and the committed CI census. They do not raise any wait.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _shell_commands(source: str) -> str:
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


class QA2PR79OpeningsTests(unittest.TestCase):
    def test_test_action_does_not_wait_for_debugger(self) -> None:
        source = _read("apps/ios/project.yml")
        self.assertRegex(source, r"(?m)^\s*debugEnabled:\s*false\s*$")

    def test_test_action_disables_main_thread_checker_and_activity_mode(self) -> None:
        source = _read("apps/ios/project.yml")
        self.assertRegex(source, r"(?m)^\s*disableMainThreadChecker:\s*true\s*$")
        self.assertRegex(source, r"(?m)^\s*OS_ACTIVITY_DT_MODE:\s*NO\s*$")

    def test_recovery_export_waits_for_share_sheet_chrome_not_system_copy(self) -> None:
        source = _read("apps/ios/Tests/ObserveRecoveryUITests/RecoveryUITests.swift")
        self.assertNotIn('descendants(matching: .any)["Copy"]', source)
        self.assertNotIn('buttons["Copy"]', source)
        self.assertIn('navigationBars["UIActivityView"]', source)
        self.assertIn('buttons["Export recovery diagnostics"].tap()', source)
        existence = [
            int(match)
            for match in re.findall(r"waitForExistence\(timeout:\s*(\d+)", source)
        ]
        waits = [
            int(match)
            for match in re.findall(r"wait\(for:[^\n]*timeout:\s*(\d+)", source)
        ]
        # Job 123296368592: hide is the Key recovery toolbar (positive exists),
        # not wait(for: exists == false). Banner 15s; toolbar/reopen/export 5s.
        self.assertEqual(existence, [15, 5, 5, 5])
        self.assertEqual(waits, [])
        self.assertNotIn("timeout: 90", source)

    def test_recovery_ui_waits_do_not_exceed_main(self) -> None:
        source = _read("apps/ios/Tests/ObserveRecoveryUITests/RecoveryUITests.swift")
        timeouts = [int(match) for match in re.findall(r"timeout:\s*(\d+)", source)]
        # Job 123296368592: banner 15s; Key recovery / banner-again / export 5s.
        self.assertEqual(timeouts, [15, 5, 5, 5])
        self.assertNotIn("timeout: 90", source)

    def test_recovery_teardown_dismisses_sheet_and_terminates(self) -> None:
        source = _read("apps/ios/Tests/ObserveRecoveryUITests/RecoveryUITests.swift")
        self.assertIn("override func tearDown()", source)
        self.assertIn('otherElements["PopoverDismissRegion"]', source)
        self.assertIn("app.terminate()", source)

    def test_recovery_dismiss_waits_on_key_recovery_not_any_exists_false(self) -> None:
        """Job 123296368592: Dismiss VisiblePoint was the button center (71.3, 195.2)
        inside frame {X:16,Y:185,W:110.67,H:20.33}. Key recovery was already in
        the AX tree at 06:24:55.909; exists==false on the pre-tap
        descendants(.any) firstMatch then walked the tree until 06:25:04.390
        (empty match) and missed the 5s wait. Wait on that toolbar instead.
        """
        tests = _read("apps/ios/Tests/ObserveRecoveryUITests/RecoveryUITests.swift")
        self.assertNotIn("exists == false", tests)
        self.assertNotIn("expectation(for:", tests)
        self.assertNotIn("NSPredicate", tests)
        self.assertNotRegex(tests, r"sleep\(|Task\.sleep|Thread\.sleep")
        self.assertRegex(
            tests,
            r'buttons\["Dismiss notice"\]\.tap\(\)\s+'
            r'let reopen = app\.buttons\["Key recovery"\]\s+'
            r'XCTAssertTrue\(reopen\.waitForExistence\(timeout: 5\)',
        )
        schema = _read("apps/ios/Tests/ObserveSchemaTests/SchemaTests.swift")
        self.assertIn("testDismissNoticeHidesImmediatelyAndRetryDoesNotRestoreIt", schema)

    def test_ios_script_captures_failure_diagnostics(self) -> None:
        script = _read("apps/ios/Scripts/test_ios_observe.sh")
        workflow = _read(".github/workflows/ci.yml")
        self.assertIn("failure-diagnostics", script)
        self.assertIn("log show", script)
        self.assertIn("launchctl list", script)
        self.assertRegex(script, r"uptime|vm_stat")
        self.assertIn("failure-diagnostics", workflow)

    def test_ios_observe_does_not_block_on_bootstatus_before_compile(self) -> None:
        """Job 123574866576 attempt 2: annotation
        'The job has exceeded the maximum execution time of 15m0s'.
        bootstatus -b ran 16:19:56–16:24:10 (Elapsed=04:11, Data Migration /
        System App) after a 3m text simctl list. xcodebuild compiled until
        16:30:36; ObserveSchemaTests launched at 16:31:38 with
        wait_for_debugger=1; cancelled at 16:31:56. RecoveryUITests
        scheduling.log was empty; no Test Case line. Kick boot in the
        background so compile overlaps the simulator cold start. Do not
        raise the 15m job timeout.
        """
        script = _read("apps/ios/Scripts/test_ios_observe.sh")
        commands = _shell_commands(script)
        workflow = _read(".github/workflows/ci.yml")
        self.assertNotRegex(commands, r"simctl\s+bootstatus")
        self.assertNotRegex(commands, r"(?m)^\s*sleep\b")
        self.assertIn('xcrun simctl boot "$SIMULATOR_ID"', commands)
        self.assertIn("xcodebuild test", commands)
        boot = commands.index('xcrun simctl boot "$SIMULATOR_ID"')
        compile_at = commands.index("xcodebuild test")
        self.assertLess(boot, compile_at)
        between = commands[boot:compile_at]
        self.assertRegex(between, r"\|\|\s*true\s*&")
        self.assertNotIn("wait ", between)
        self.assertNotRegex(between, r"simctl\s+bootstatus")
        before_test = commands[:compile_at]
        # Job 124571864334: `simctl list devices available -j` blocked 2m11s
        # on the pull_request runner (push listed in 5s). Never enumerate
        # the device catalog; create one iPhone from runtimes/devicetypes.
        self.assertNotRegex(before_test, r"simctl\s+list\s+devices")
        self.assertIn('select_ios_simulator.py" --create', script)
        self.assertIn('select_ios_simulator.py" --create', commands)
        self.assertRegex(
            workflow,
            r"(?m)^  ios-observe-tests:\n"
            r"(?:    #.*\n)*"
            r"    if: github\.event_name != 'pull_request' \|\| "
            r"github\.event\.pull_request\.head\.repo\.full_name != github\.repository\n"
            r"    runs-on: macos-latest\n"
            r"    timeout-minutes: 15\n",
        )

    def test_launch_fault_workflow_labels_load_as_smoke(self) -> None:
        workflow = _read(".github/workflows/launch-fault-stress.yml")
        self.assertRegex(workflow, r"(?i)smoke")
        self.assertIn("python -m unittest tests.test_launch_faults", workflow)
        self.assertNotRegex(
            workflow,
            r"python -m unittest tests\.test_launch_faults.*\|\|\s*true",
        )
        self.assertRegex(
            workflow,
            r"set -o pipefail[\s\S]*python -m unittest tests\.test_launch_faults[^\n]*\|\s*tee",
        )

    def test_approval_review_text_is_escaped_not_raw(self) -> None:
        package = _read("apps/macos/Sources/RunSpecimenCore/RSBA2Package.swift")
        session = _read("apps/ios/Sources/RunSpecimenObserve/Services/CompanionSession.swift")
        self.assertIn("public static func displayText", package)
        self.assertIn("Nonce: \\(displayText(fields.nonce))", package)
        self.assertIn("nonce \\(RSBA2Package.displayText(nonce))", session)
        self.assertIn(".format", package)
        self.assertIn(".control", package)

    def test_openings_module_does_not_import_third_party_yaml(self) -> None:
        source = _read("tests/test_qa2_pr79_openings.py")
        self.assertNotRegex(source, r"(?m)^\s*(import yaml|from yaml\b)")

    def test_qa_census_discloses_seventeen_ios_failures(self) -> None:
        census = _read("docs/QA2_CI_CENSUS_2026-10-27.md")
        summary = json.loads(_read("evidence/QA2-ci-census-summary.json"))
        rows = _read("evidence/QA2-ios-observe-tests-all-attempts.tsv").splitlines()[1:]
        failures = [row for row in rows if "\tfailure\t" in row]
        self.assertIn("17 failures", census)
        self.assertEqual(summary["outcomes"]["failure"], 17)
        self.assertEqual(len(failures), 17)

    def test_schema_pairing_tests_use_isolated_storage_defaults(self) -> None:
        source = _read("apps/ios/Tests/ObserveSchemaTests/SchemaTests.swift")
        self.assertNotIn("let defaults = UserDefaults.standard", source)
        self.assertIn("let defaults = CompanionSession.storageDefaults", source)

    def test_companion_session_declares_storage_defaults_once(self) -> None:
        source = _read("apps/ios/Sources/RunSpecimenObserve/Services/CompanionSession.swift")
        declarations = re.findall(r"static var storageDefaults:", source)
        self.assertEqual(len(declarations), 1)

    def test_recovery_export_content_is_unit_tested(self) -> None:
        tests = _read("apps/ios/Tests/ObserveSchemaTests/SchemaTests.swift")
        self.assertIn("rotationRecoveryDiagnostics.contains", tests)
        self.assertIn("Recovery evidence is retained", tests)

    def test_cancellation_target_uses_isolated_session_storage(self) -> None:
        source = _read("apps/ios/Tests/PhonePeerCancellationTests/PhonePeerCancellationXCTests.swift")
        self.assertIn("IsolatedCompanionSessionTests", source)
        self.assertNotRegex(source, r"class PhonePeerCancellationXCTests:\s*XCTestCase")
        for path in (ROOT / "apps/ios/Sources").rglob("*.swift"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "UserDefaults.standard",
                text,
                f"{path} must not read the shared defaults suite",
            )
