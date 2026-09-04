"""Loopback-only, read-only dashboard for a single RunSpecimen contract.

The dashboard is deliberately a *guide*, not a second execution API.  The CLI
remains the sole enforcement boundary and approval remains a real TTY action.
"""

from __future__ import annotations

import html
import json
import shlex
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from runspecimen.contract import load_contract
from runspecimen.paths import resolve_workspace
from runspecimen.status import status_for


def dashboard_document(*, workspace: Path, contract_path: Path, status: dict[str, Any]) -> str:
    """Render a self-contained dashboard without third-party browser assets."""
    contract = load_contract(contract_path)
    escaped_status = html.escape(json.dumps(status, indent=2, sort_keys=True, default=str))
    workspace_s = html.escape(str(workspace))
    contract_s = html.escape(str(contract_path))
    phase = html.escape(str(status["phase"]))
    workspace_arg = shlex.quote(str(workspace))
    contract_arg = shlex.quote(str(contract_path))
    campaign_arg = shlex.quote(contract.campaign_id)
    run_arg = shlex.quote(contract.run_id)
    approve = f"runspecimen approve --workspace {workspace_arg} --contract {contract_arg}"
    commands = [
        ("Validate", f"runspecimen validate --workspace {workspace_arg} --contract {contract_arg}"),
        ("Approve in a terminal", approve),
        ("Preflight", f"runspecimen preflight --workspace {workspace_arg} --contract {contract_arg}"),
        ("Run once", f"runspecimen run --workspace {workspace_arg} --contract {contract_arg}"),
        ("Postflight", f"runspecimen postflight --workspace {workspace_arg} --contract {contract_arg}"),
        ("Verify receipt", f"runspecimen verify --workspace {workspace_arg} --contract {contract_arg} --campaign-id {campaign_arg} --run-id {run_arg}"),
    ]
    steps = "".join(
        f"<li><strong>{html.escape(label)}</strong><code>{html.escape(command)}</code></li>"
        for label, command in commands
    )
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>RunSpecimen — {html.escape(contract.campaign_id)} / {html.escape(contract.run_id)}</title>
<style>body{{font:16px system-ui,sans-serif;max-width:940px;margin:3rem auto;padding:0 1rem;color:#172033;background:#fbfcfe}}h1{{margin-bottom:.2rem}}.badge{{display:inline-block;background:#e8eefc;border-radius:999px;padding:.2rem .65rem;font-weight:700}}.warning{{background:#fff3d6;border-left:4px solid #d99800;padding:1rem;margin:1.5rem 0}}code,pre{{display:block;white-space:pre-wrap;overflow-wrap:anywhere;background:#101828;color:#e6edf7;padding:.7rem;border-radius:6px;margin:.45rem 0 1rem}}li{{margin:1rem 0}}button{{padding:.4rem .7rem}}small{{color:#536174}}</style></head>
<body><h1>RunSpecimen local dashboard</h1><p><span class=\"badge\">{phase}</span></p>
<p><strong>Workspace:</strong> {workspace_s}<br><strong>Contract:</strong> {contract_s}</p>
<div class=\"warning\"><strong>Safety boundary:</strong> this page is read-only. It cannot approve or execute a run. Approval must be typed by a human in a real terminal; use the commands below one at a time.</div>
<h2>Guided lifecycle</h2><ol>{steps}</ol>
<h2>Current evidence</h2><pre id=\"status\">{escaped_status}</pre>
<p><button onclick=\"refreshStatus()\">Refresh status</button> <small>Reads only this dashboard's selected contract and workspace.</small></p>
<script>async function refreshStatus(){{const r=await fetch('/api/status');document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2);}}</script>
</body></html>"""


def make_handler(*, workspace: Path, contract_path: Path):
    """Create a handler restricted to one resolved workspace and contract."""
    workspace = resolve_workspace(workspace)
    contract_path = contract_path.resolve()
    contract = load_contract(contract_path)

    def current_status() -> dict[str, Any]:
        return status_for(
            workspace=workspace,
            campaign_id=contract.campaign_id,
            run_id=contract.run_id,
            contract_path=contract_path,
        )

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = dashboard_document(
                    workspace=workspace, contract_path=contract_path, status=current_status()
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
            elif self.path == "/api/status":
                body = json.dumps(current_status(), sort_keys=True, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
            else:
                body = b'{"error":"not found"}'
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            self.send_error(405, "dashboard is read-only; use the CLI lifecycle")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return DashboardHandler


def start_dashboard(*, workspace: Path, contract_path: Path, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Bind a dashboard to loopback only and return its server and URL."""
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(
        workspace=workspace, contract_path=contract_path
    ))
    host, selected_port = server.server_address[:2]
    return server, f"http://{host}:{selected_port}/"
