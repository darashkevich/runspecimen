"""Installed-product onboarding must never overwrite or approve a workspace."""

import contextlib
import io
from unittest.mock import patch

from tests.helpers import RunSpecimenTestCase
from runspecimen.cli import main
from runspecimen.contract import check_contract_paths, load_contract
from runspecimen.demo import init_demo
from runspecimen.errors import RunSpecimenError


class TestDemoCLI(RunSpecimenTestCase):
    def test_demo_creates_valid_unapproved_contract_without_outputs(self):
        destination = self.ws / "new demo"
        result = init_demo(destination)
        contract = load_contract(destination / "contract.json")
        check_contract_paths(contract, destination)
        self.assertFalse(result["approved"])
        self.assertFalse(result["executed"])
        self.assertFalse((destination / ".runspecimen").exists())
        self.assertEqual(list((destination / "outputs").iterdir()), [])
        self.assertEqual(contract.postflight.json_equals[1].equals, 338350)

    def test_demo_refuses_existing_directory_without_mutation(self):
        sentinel = self.ws / "important.txt"
        sentinel.write_text("preserve me", encoding="utf-8")
        before = sorted(self.ws.rglob("*"))
        with self.assertRaises(RunSpecimenError):
            init_demo(self.ws)
        self.assertEqual(sorted(self.ws.rglob("*")), before)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")

    def test_cli_missing_contract_has_readable_error_without_traceback(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            code = main(["validate", "--workspace", str(self.ws), "--contract", str(self.ws / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("RunSpecimen error:", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())

    def test_interrupted_dashboard_does_not_claim_no_approval_exists(self):
        error = io.StringIO()
        with patch("runspecimen.dashboard.start_dashboard", side_effect=KeyboardInterrupt), contextlib.redirect_stderr(error):
            code = main(["dashboard", "--workspace", str(self.ws), "--contract", "unused.json"])
        self.assertEqual(code, 130)
        self.assertIn("inspect status", error.getvalue())
        self.assertNotIn("no approval was recorded", error.getvalue())
