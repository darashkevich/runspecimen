"""Opt-in, fail-closed companion endpoint for observation + remote human confirm.

Hard rules (see docs/ADR-003-ios-companion-observation.md and
docs/ADR-004-remote-human-confirm.md):
- Disabled unless explicitly enabled with a pairing token
- can_approve stays False for all clients (plugins/agents included)
- Lifecycle verb paths (approve/run/preflight/...) stay forbidden
- Remote confirm settles only a Mac-armed pending challenge via
  POST /v1/remote-confirm with pairing + challenge + APPROVE
- POST /v1/remote-confirm-refuse consumes pending with challenge + reason (no approval)
- Challenge secret is never returned over HTTP (Mac TTY / local file only)
- Default bind is loopback (pairing token OK over cleartext)
- Non-loopback bind requires --allow-lan, a private/Tailscale address, and TLS
- Remote-confirm refuses cleartext off loopback; no public internet control plane
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from runspecimen.companion_tls import (
    CompanionTLSMaterial,
    generate_ephemeral_tls,
    host_requires_tls,
    load_tls_material,
    remote_confirm_transport_ok,
    wrap_server_socket,
)
from runspecimen.contract import load_contract
from runspecimen.errors import ApprovalError, RunSpecimenError
from runspecimen.paths import run_state_dir
from runspecimen.remote_confirm import (
    CLAIM_TEXT,
    NOT_EQUIVALENT_TO,
    load_pending,
    public_pending_view,
    refuse_remote_confirm,
    run_ontology_chips,
    settle_remote_confirm,
)
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

# Narrow exception: remote-confirm is allowed; it must not match "approve".
ALLOWED_MUTATING_ROUTES = frozenset({"/v1/remote-confirm", "/v1/remote-confirm-refuse"})

CAPABILITIES = {
    "product": "RunSpecimen",
    "mode": "observe",
    "api_version": 1,
    "can_approve": False,
    "can_execute": False,
    "can_mutate_lifecycle": False,
    "can_remote_confirm": False,
    "can_request_attention": True,
    "can_open_local_dashboard": True,
    "transport": "loopback-http-or-lan-tls-opt-in",
    "transport_policy": {
        "loopback": "pairing-token-over-http-ok",
        "non_loopback": "tls-required-plus-pairing-token",
        "remote_confirm_cleartext_off_loopback": False,
        "public_internet_control_plane": False,
        "recommended_path": "tailscale-or-private-lan-with-tls",
    },
    "boundary": (
        "Observation, attention, and optional Mac-armed remote human confirm. "
        "can_approve stays false for plugins/agents. Local TTY APPROVE remains "
        "the primary path; remote confirm is not TTY-equivalent and is not an OS sandbox."
    ),
    "adr": "docs/ADR-004-remote-human-confirm.md",
    "adr_observe": "docs/ADR-003-ios-companion-observation.md",
    "ios_bundle_id": "com.darashkevich.runspecimen.observe",
    "mac_companion_bundle_id": "com.darashkevich.runspecimen.companion",
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
    if addr.is_private or addr.is_link_local or getattr(addr, "is_unique_local", False):
        return
    if isinstance(addr, ipaddress.IPv4Address) and ipaddress.ip_address("100.64.0.0") <= addr <= ipaddress.ip_address(
        "100.127.255.255"
    ):
        return
    raise RunSpecimenError(
        f"companion refuses public bind address {host}; use loopback, LAN private, or Tailscale IP"
    )


def path_is_forbidden(path: str) -> bool:
    lowered = path.lower().rstrip("/") or "/"
    if lowered in ALLOWED_MUTATING_ROUTES:
        return False
    return any(marker in lowered for marker in FORBIDDEN_PATH_MARKERS)


def make_handler(
    *,
    workspace: Path,
    contract_path: Path,
    pairing_token: str,
    on_attention: Callable[[dict[str, Any]], None] | None = None,
    on_open_dashboard: Callable[[], None] | None = None,
    on_remote_confirmed: Callable[[dict[str, Any]], None] | None = None,
):
    """Create a companion handler scoped to one workspace + contract."""
    workspace = workspace.resolve()
    contract_path = contract_path.resolve()
    contract = load_contract(contract_path)
    attention_lock = threading.Lock()
    attention_log: list[dict[str, Any]] = []
    confirm_lock = threading.Lock()
    rate_lock = threading.Lock()
    # Simple in-memory rate limit: max attempts per window per peer.
    rate_window_sec = 60.0
    rate_max_attempts = 20
    rate_events: list[float] = []

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

    def remote_confirm_view() -> dict[str, Any]:
        state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
        pending = load_pending(state_dir)
        return public_pending_view(pending)

    def capabilities_doc() -> dict[str, Any]:
        view = remote_confirm_view()
        doc = dict(CAPABILITIES)
        doc["can_approve"] = False
        doc["can_remote_confirm"] = bool(view.get("can_remote_confirm"))
        doc["remote_confirm"] = {
            "pending": bool(view.get("pending")),
            "not_equivalent_to": NOT_EQUIVALENT_TO,
            "claim": CLAIM_TEXT,
        }
        return doc

    def rate_limit_ok() -> bool:
        now = time.time()
        with rate_lock:
            while rate_events and rate_events[0] < now - rate_window_sec:
                rate_events.pop(0)
            if len(rate_events) >= rate_max_attempts:
                return False
            rate_events.append(now)
            return True

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
            self._respond(
                code,
                json.dumps(
                    {
                        "error": message,
                        "can_approve": False,
                        "can_remote_confirm": False,
                    }
                ).encode("utf-8"),
            )

        def _authorized(self) -> bool:
            auth = self.headers.get("Authorization", "")
            token = None
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
            if token is None:
                token = self.headers.get("X-RunSpecimen-Pairing-Token")
            if not _constant_time_token_ok(token, pairing_token):
                self._error(401, "Pairing token required. Companion cannot approve via plugins.")
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
                self._respond(
                    200,
                    json.dumps(
                        {
                            "ok": True,
                            "mode": "observe",
                            "can_approve": False,
                            "can_execute": False,
                            "can_remote_confirm": False,
                        },
                        sort_keys=True,
                    ).encode("utf-8"),
                )
                return
            if not self._authorized():
                return
            try:
                if route == "/v1/capabilities":
                    self._respond(200, json.dumps(capabilities_doc(), sort_keys=True).encode("utf-8"))
                    return
                if route == "/v1/status":
                    doc = current_status()
                    view = remote_confirm_view()
                    pending = load_pending(
                        run_state_dir(workspace, contract.campaign_id, contract.run_id)
                    )
                    if view.get("pending"):
                        view = dict(view)
                        view["chips"] = run_ontology_chips(
                            contract=contract,
                            workspace=workspace,
                            pending=pending,
                        )
                    doc["companion"] = {
                        "mode": "observe",
                        "can_approve": False,
                        "can_execute": False,
                        "can_remote_confirm": bool(view.get("can_remote_confirm")),
                        "remote_confirm": view,
                        "note": (
                            "Plugins cannot approve. Remote human confirm requires a Mac-armed "
                            "challenge typed with APPROVE on the paired companion; not TTY-equivalent."
                        ),
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
                            "note": "Attention only. Use remote-confirm or Mac TTY for approval.",
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
            if route == "/v1/remote-confirm":
                if not remote_confirm_transport_ok(
                    client_address=self.client_address,
                    connection=self.connection,
                ):
                    self._error(
                        403,
                        "remote-confirm refuses cleartext off loopback; "
                        "use TLS (--allow-lan enables ephemeral TLS) or Tailscale.",
                    )
                    return
                if not rate_limit_ok():
                    self._error(429, "Too many remote-confirm attempts; slow down.")
                    return
                challenge = str(payload.get("challenge") or "")
                phrase = str(payload.get("phrase") or payload.get("confirm") or "")
                with confirm_lock:
                    try:
                        approval = settle_remote_confirm(
                            contract_path=contract_path,
                            workspace=workspace,
                            challenge=challenge,
                            phrase=phrase,
                        )
                    except ApprovalError as exc:
                        self._error(403, str(exc))
                        return
                    except (RunSpecimenError, OSError, ValueError, KeyError, TypeError) as exc:
                        self._error(503, f"Remote confirm failed: {exc}")
                        return
                if on_remote_confirmed is not None:
                    on_remote_confirmed(approval)
                self._respond(
                    200,
                    json.dumps(
                        {
                            "ok": True,
                            "settled": True,
                            "can_approve": False,
                            "confirm_channel": approval.get("confirm_channel"),
                            "confirm_evidence": approval.get("confirm_evidence"),
                            "approval": {
                                "campaign_id": approval.get("campaign_id"),
                                "run_id": approval.get("run_id"),
                                "contract_hash": approval.get("contract_hash"),
                                "expires_at_unix": approval.get("expires_at_unix"),
                                "confirm_channel": approval.get("confirm_channel"),
                            },
                            "note": CLAIM_TEXT,
                        },
                        sort_keys=True,
                        default=str,
                    ).encode("utf-8"),
                )
                return
            if route == "/v1/remote-confirm-refuse":
                if not remote_confirm_transport_ok(
                    client_address=self.client_address,
                    connection=self.connection,
                ):
                    self._error(
                        403,
                        "remote-confirm-refuse refuses cleartext off loopback; "
                        "use TLS (--allow-lan enables ephemeral TLS) or Tailscale.",
                    )
                    return
                if not rate_limit_ok():
                    self._error(429, "Too many remote-confirm attempts; slow down.")
                    return
                challenge = str(payload.get("challenge") or "")
                reason = str(payload.get("reason") or "")
                with confirm_lock:
                    try:
                        refused = refuse_remote_confirm(
                            contract_path=contract_path,
                            workspace=workspace,
                            challenge=challenge,
                            reason=reason,
                        )
                    except ApprovalError as exc:
                        self._error(403, str(exc))
                        return
                    except (RunSpecimenError, OSError, ValueError, KeyError, TypeError) as exc:
                        self._error(503, f"Remote confirm refuse failed: {exc}")
                        return
                self._respond(
                    200,
                    json.dumps(
                        {
                            "ok": True,
                            "refused": True,
                            "can_approve": False,
                            "confirm_channel": refused.get("confirm_channel"),
                            "reason": refused.get("reason"),
                            "note": refused.get("note"),
                        },
                        sort_keys=True,
                        default=str,
                    ).encode("utf-8"),
                )
                return
            self._error(
                405,
                "Use POST /v1/remote-confirm (paired + Mac challenge + APPROVE), "
                "POST /v1/remote-confirm-refuse (challenge + reason), "
                "or Mac TTY approve. Plugins cannot approve.",
            )

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
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
    on_attention: Callable[[dict[str, Any]], None] | None = None,
    on_open_dashboard: Callable[[], None] | None = None,
    on_remote_confirmed: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[ThreadingHTTPServer, str, dict[str, Any]]:
    """Bind the companion server. Fail closed unless bind + TLS policy passes."""
    if not pairing_token or len(pairing_token) < 16:
        raise RunSpecimenError("companion requires a pairing token of at least 16 characters")
    if not 0 <= port <= 65535:
        raise RunSpecimenError("companion port must be between 0 and 65535")
    if not workspace.is_dir():
        raise RunSpecimenError(f"workspace is not a directory: {workspace}")
    assert_bind_allowed(host, allow_lan=allow_lan)

    needs_tls = host_requires_tls(host)
    tls_material: CompanionTLSMaterial | None = None
    if tls_cert is not None or tls_key is not None:
        if tls_cert is None or tls_key is None:
            raise RunSpecimenError("companion TLS requires both --tls-cert and --tls-key")
        tls_material = load_tls_material(cert_path=tls_cert, key_path=tls_key)
    elif needs_tls:
        tls_dir = Path(workspace) / ".runspecimen" / "companion_tls"
        tls_material = generate_ephemeral_tls(bind_host=host, destination=tls_dir)

    handler = make_handler(
        workspace=workspace,
        contract_path=contract_path,
        pairing_token=pairing_token,
        on_attention=on_attention,
        on_open_dashboard=on_open_dashboard,
        on_remote_confirmed=on_remote_confirmed,
    )
    server = ThreadingHTTPServer((host, port), handler)
    if tls_material is not None:
        wrap_server_socket(server, tls_material)
    bound_host, selected_port = server.server_address[:2]
    scheme = "https" if tls_material is not None else "http"
    url = f"{scheme}://{bound_host}:{selected_port}/"
    meta: dict[str, Any] = {
        "ok": True,
        "url": url,
        "host": bound_host,
        "port": selected_port,
        "scheme": scheme,
        "tls": tls_material is not None,
        "allow_lan": allow_lan,
        "mode": "observe",
        "can_approve": False,
        "can_execute": False,
        "can_remote_confirm": False,
        "pairing_required": True,
        "ios_bundle_id": CAPABILITIES["ios_bundle_id"],
        "mac_companion_bundle_id": CAPABILITIES["mac_companion_bundle_id"],
        "shipping_channel": "TestFlight/later (no App Store submit in this change set)",
        "adr": "docs/ADR-004-remote-human-confirm.md",
        "adr_observe": "docs/ADR-003-ios-companion-observation.md",
        "note": (
            "Remote confirm requires Mac-side `remote-confirm arm` first. "
            "Challenge is shown only on the Mac. Non-loopback binds require TLS; "
            "Tailscale is the recommended path. No public internet control plane."
        ),
    }
    if tls_material is not None:
        meta.update(tls_material.as_meta())
    return server, url, meta
