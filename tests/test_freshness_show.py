"""`freshness show` reads a stored report and does not recompute one."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest

from tests.helpers import SRC, RunSpecimenTestCase

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


if __name__ == "__main__":
    unittest.main()
