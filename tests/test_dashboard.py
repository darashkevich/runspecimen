"""Tests for the loopback-only, read-only dashboard."""

from __future__ import annotations

import html
import shlex
import sys
import unittest
from unittest.mock import patch

from tests.helpers import SRC, RunSpecimenTestCase, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.dashboard import dashboard_document, make_handler, start_dashboard


class TestDashboard(RunSpecimenTestCase):
    def test_dashboard_is_loopback_read_only_and_scoped_to_contract(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        handler = make_handler(workspace=self.ws, contract_path=contract_path)
        self.assertTrue(issubclass(handler, object))
        page = dashboard_document(
            workspace=self.ws.resolve(),
            contract_path=contract_path.resolve(),
            status={"phase": "none"},
        )
        self.assertIn("Safety boundary", page)
        self.assertIn("Approve in a terminal", page)
        self.assertNotIn("/api/run", page)

    def test_dashboard_binds_loopback_only(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        with patch("runspecimen.dashboard.ThreadingHTTPServer") as server_cls:
            server = server_cls.return_value
            server.server_address = ("127.0.0.1", 43210)
            _server, url = start_dashboard(
                workspace=self.ws, contract_path=contract_path, port=0
            )
        self.assertEqual(server_cls.call_args.args[0], ("127.0.0.1", 0))
        self.assertEqual(url, "http://127.0.0.1:43210/")

    def test_dashboard_shell_quotes_copyable_paths(self) -> None:
        spaced = self.ws / "workspace with spaces"
        spaced.mkdir()
        (spaced / "work").mkdir()
        (spaced / "work" / "script.py").write_text("print('ok')\n", encoding="utf-8")
        contract_path = write_contract(spaced, "contract with spaces.json", base_contract())
        page = dashboard_document(
            workspace=spaced.resolve(),
            contract_path=contract_path.resolve(),
            status={"phase": "none"},
        )
        rendered = html.unescape(page)
        self.assertIn(shlex.quote(str(spaced.resolve())), rendered)
        self.assertIn(shlex.quote(str(contract_path.resolve())), rendered)


if __name__ == "__main__":
    unittest.main()
