"""`freshness show` reads a stored report and does not recompute one."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest

from tests.helpers import SRC, RunSpecimenTestCase, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.cli import main


class FreshnessShowTests(RunSpecimenTestCase):
    def test_missing_report_fails_without_writing(self) -> None:
        before = {path.relative_to(self.ws) for path in self.ws.rglob("*")}
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "freshness",
                    "show",
                    "--workspace",
                    str(self.ws),
                    "--campaign-id",
                    "camp",
                    "--run-id",
                    "run-a",
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("freshness report not found", stderr.getvalue())
        after = {path.relative_to(self.ws) for path in self.ws.rglob("*")}
        self.assertEqual(before, after)

    def test_evaluate_does_not_write_freshness_report(self) -> None:
        cpath = write_contract(self.ws, "c.json", base_contract())
        before = {path.relative_to(self.ws) for path in self.ws.rglob("*") if path.is_file()}
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "freshness",
                    "evaluate",
                    "--workspace",
                    str(self.ws),
                    "--contract",
                    str(cpath),
                ]
            )
        self.assertIn(code, (0, 1))
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["wrote"])
        written = [
            path
            for path in self.ws.rglob("*")
            if path.is_file() and path.relative_to(self.ws) not in before
        ]
        self.assertFalse(
            any(path.name == "freshness_report.json" for path in written),
            written,
        )


if __name__ == "__main__":
    unittest.main()
