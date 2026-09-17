"""Opt-in, fail-closed companion endpoint for remote *observation*.

This module intentionally mirrors the loopback dashboard safety posture while
allowing an authenticated phone client on a human-opted local network bind.

Hard rules (see docs/ADR-003-ios-companion-observation.md):
- Disabled unless explicitly enabled with a pairing token
- Never exposes approve / run / preflight / postflight / execute
- Does not write lifecycle state, approvals, events, or certificates
- Default bind is loopback; LAN bind requires --allow-lan and a private address
- Agents must not be given a path to inject TTY APPROVE via this API
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from runspecimen.contract import load_contract
from runspecimen.errors import RunSpecimenError
from runspecimen.status import status_for

FORBIDDEN_PATH_MARKERS = (
    "approve",
    "run",
    "preflight",
    "postflight",
    "execute",
    "pty",
    "inject",
)

CAPABILITIES = {
    "product": "RunSpecimen",
    "mode": "observe",
    "api_version": 1,
    "can_approve": False,
    "can_execute": False,
    "can_mutate_lifecycle": False,
    "can_request_attention": True,
    "can_open_local_dashboard": True,
    "transport": "local-network-opt-in",
    "boundary": (
        "Observation and attention only. Approval remains real-TTY APPROVE on the Mac. "
        "This endpoint is not an OS sandbox and cannot approve or execute."
    ),
    "adr": "docs/ADR-003-ios-companion-observation.md",
}


def generate_pairing_token() -> str:
    """Return a high-entropy opaque pairing secret for bearer auth."""
    return secrets.token_urlsafe(32)


def _constant_time_token_ok(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    left = hashlib.sha256(provided.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


def assert_bind_allowed(host: str, *, allow_lan: bool) -> None:
    """Refuse unsafe binds. Fail closed unless allow_lan + private/link-local/loopback."""
    normalized = host.strip().lower()
    if normalized in {"localhost"}:
        return
    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise RunSpecimenError(
            f"companion bind host must be an IP address or localhost, not {host!r}"
        ) from exc
    if addr.is_loopback:
        return
    if not allow_lan:
        raise RunSpecimenError(
            "companion refuses non-loopback bind without --allow-lan "
            "(see docs/ADR-003-ios-companion-observation.md)"
        )
    if addr.is_unspecified:
        raise RunSpecimenError(
            "companion refuses unspecified bind (0.0.0.0 / ::); pass a concrete private address"
        )
    if addr.is_multicast or addr.is_reserved:
        raise RunSpecimenError(f"companion refuses bind address {host}")
    # Private, link-local, and IPv6 unique-local are allowed with --allow-lan.
    if addr.is_private or addr.is_link_local or getattr(addr, "is_unique_local", False):
        return
    # Tailscale userspace often uses 100.x (shared CGNAT / RFC6598).
    if isinstance(addr, ipaddress.IPv4Address) and ipaddress.ip_address("100.64.0.0") <= addr <= ipaddress.ip_address(
        "100.127.255.255"
    ):
        return
    raise RunSpecimenError(
        f"companion refuses public bind address {host}; use loopback, LAN private, or Tailscale IP"
    )


def path_is_forbidden(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in FORBIDDEN_PATH_MARKERS)


def make_handler(
    *,
    workspace: Path,
    contract_path: Path,
    pairing_token: str,
    on_attention: Callable[[dict[str, Any]], None] | None = None,
    on_open_dashboard: Callable[[], None] | None = None,
):
    """Create a read-mostly companion handler scoped to one workspace + contract."""
    workspace = workspace.resolve()
    contract_path = contract_path.resolve()
    contract = load_contract(contract_path)
    attention_lock = threading.Lock()
    attention_log: list[dict[str, Any]] = []

    def current_status() -> dict[str, Any]:
        live = load_contract(contract_path)
        if live.contract_hash != contract.contract_hash:
            raise RunSpecimenError("Contract changed since companion startup; restart companion.")
        return status_for(
            workspace=workspace,
            campaign_id=contract.campaign_id,
            run_id=contract.run_id,
            contract_path=contract_path,
        )

    class CompanionHandler(BaseHTTPRequestHandler):
        server_version = "RunSpecimenCompanion"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def _respond(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _error(self, code: int, message: str) -> None:
            self._respond(code, json.dumps({"error": message, "can_approve": False}).encode("utf-8"))

        def _authorized(self) -> bool:
            auth = self.headers.get("Authorization", "")
            token = None
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
            if token is None:
                token = self.headers.get("X-RunSpecimen-Pairing-Token")
            if not _constant_time_token_ok(token, pairing_token):
                self._error(401, "Pairing token required. Companion cannot approve or execute.")
                return False
            return True

        def _route(self) -> str:
            return urlparse(self.path).path.rstrip("/") or "/"

        def do_GET(self) -> None:  # noqa: N802
            route = self._route()
            if path_is_forbidden(route):
                self._error(403, "Lifecycle mutation paths are forbidden on the companion.")
                return
            if route == "/v1/health":
                # Health is unauthenticated so the operator can confirm the listener is up
                # before pasting the pairing token into the phone. It reveals no run evidence.
                self._respond(
                    200,
                    json.dumps(
                        {
                            "ok": True,
                            "mode": "observe",
                            "can_approve": False,
                            "can_execute": False,
                        },
                        sort_keys=True,
                    ).encode("utf-8"),
                )
                return
            if not self._authorized():
                return
            try:
                if route == "/v1/capabilities":
                    self._respond(200, json.dumps(CAPABILITIES, sort_keys=True).encode("utf-8"))
                    return
                if route == "/v1/status":
                    doc = current_status()
                    doc["companion"] = {
                        "mode": "observe",
                        "can_approve": False,
                        "can_execute": False,
                        "note": "Approve only via real TTY on the Mac.",
                    }
                    self._respond(200, json.dumps(doc, sort_keys=True, default=str).encode("utf-8"))
                    return
                self._error(404, "Not found")
            except (RunSpecimenError, OSError, ValueError, KeyError, TypeError) as exc:
                self._error(503, f"Local evidence is unavailable: {exc}")

        def do_POST(self) -> None:  # noqa: N802
            route = self._route()
            if path_is_forbidden(route):
                self._error(403, "Lifecycle mutation paths are forbidden on the companion.")
                return
            if not self._authorized():
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length > 65_536:
                self._error(413, "Request body too large")
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error(400, "JSON body required")
                return
            if not isinstance(payload, dict):
                self._error(400, "JSON object required")
                return
            if route == "/v1/attention":
                entry = {
                    "message": str(payload.get("message") or "Attention requested from companion"),
                    "source": "ios-companion",
                    "mutates_lifecycle": False,
                }
                with attention_lock:
                    attention_log.append(entry)
                    # Keep memory bounded; this is a scaffold, not a durable queue.
                    del attention_log[:-32]
                if on_attention is not None:
                    on_attention(entry)
                self._respond(
                    202,
                    json.dumps(
                        {
                            "ok": True,
                            "accepted": True,
                            "mutates_lifecycle": False,
                            "can_approve": False,
                            "note": "Mac operator must still approve on-device via TTY if action is required.",
                        },
                        sort_keys=True,
                    ).encode("utf-8"),
                )
                return
            if route == "/v1/open-dashboard":
                if on_open_dashboard is not None:
                    on_open_dashboard()
                self._respond(
                    202,
                    json.dumps(
                        {
                            "ok": True,
                            "accepted": True,
                            "mutates_lifecycle": False,
                            "note": "Local dashboard open requested on Mac (loopback, read-only).",
                        },
                        sort_keys=True,
                    ).encode("utf-8"),
                )
                return
            self._error(405, "Companion is observation-only; use the Mac TTY for lifecycle commands.")

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._error(405, "Companion does not enable browser CORS control planes.")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return CompanionHandler


def start_companion(
    *,
    workspace: Path,
    contract_path: Path,
    pairing_token: str,
    host: str = "127.0.0.1",
    port: int = 0,
    allow_lan: bool = False,
    on_attention: Callable[[dict[str, Any]], None] | None = None,
    on_open_dashboard: Callable[[], None] | None = None,
) -> tuple[ThreadingHTTPServer, str, dict[str, Any]]:
    """Bind the companion server. Fail closed unless bind policy passes."""
    if not pairing_token or len(pairing_token) < 16:
        raise RunSpecimenError("companion requires a pairing token of at least 16 characters")
    if not 0 <= port <= 65535:
        raise RunSpecimenError("companion port must be between 0 and 65535")
    if not workspace.is_dir():
        raise RunSpecimenError(f"workspace is not a directory: {workspace}")
    assert_bind_allowed(host, allow_lan=allow_lan)

    handler = make_handler(
        workspace=workspace,
        contract_path=contract_path,
        pairing_token=pairing_token,
        on_attention=on_attention,
        on_open_dashboard=on_open_dashboard,
    )
    server = ThreadingHTTPServer((host, port), handler)
    bound_host, selected_port = server.server_address[:2]
    url = f"http://{bound_host}:{selected_port}/"
    meta = {
        "ok": True,
        "url": url,
        "host": bound_host,
        "port": selected_port,
        "allow_lan": allow_lan,
        "mode": "observe",
        "can_approve": False,
        "can_execute": False,
        "pairing_required": True,
        "adr": "docs/ADR-003-ios-companion-observation.md",
    }
    return server, url, meta
