"""Ephemeral TLS material for non-loopback companion binds (ADR-003 / ADR-004).

Product default:
- Loopback may stay cleartext HTTP with pairing bearer.
- Non-loopback (--allow-lan) requires TLS before the listener starts.
- Remote-confirm refuses cleartext off loopback even if a misconfigured
  cleartext socket somehow exists.
- No public internet control plane. Tailscale (or equivalent private mesh)
  is the recommended path for phone ↔ Mac.

Uses OpenSSL CLI so the default install stays dependency-free.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
import shutil
import ssl
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runspecimen.errors import RunSpecimenError


@dataclass(frozen=True)
class CompanionTLSMaterial:
    cert_path: Path
    key_path: Path
    fingerprint_sha256: str  # colon-separated uppercase hex
    fingerprint_sha256_compact: str  # lowercase hex, no colons
    ephemeral: bool

    def as_meta(self) -> dict[str, Any]:
        return {
            "tls": True,
            "tls_cert_path": str(self.cert_path),
            "tls_key_path": str(self.key_path),
            "tls_fingerprint_sha256": self.fingerprint_sha256,
            "tls_fingerprint_sha256_compact": self.fingerprint_sha256_compact,
            "tls_ephemeral": self.ephemeral,
            "tls_pin_note": (
                "Enter this SHA-256 fingerprint in the iOS Observe app when pairing "
                "over HTTPS. Prefer Tailscale. No public internet control plane."
            ),
        }


def host_requires_tls(host: str) -> bool:
    """True when the bind host is not loopback (LAN / Tailscale / etc.)."""
    normalized = host.strip().lower()
    if normalized in {"localhost"}:
        return False
    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        # Non-IP hostnames are already rejected by assert_bind_allowed.
        return True
    return not addr.is_loopback


def normalize_fingerprint(value: str) -> str:
    """Return lowercase hex without separators for constant-time compare."""
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", value or "")
    return cleaned.lower()


def fingerprint_sha256_of_pem(cert_pem: bytes | str) -> str:
    """SHA-256 fingerprint of the DER certificate (colon-separated uppercase)."""
    text = cert_pem.decode("utf-8") if isinstance(cert_pem, bytes) else cert_pem
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("-----")]
    der = base64.b64decode("".join(lines))
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def _openssl_bin() -> str:
    path = shutil.which("openssl")
    if not path:
        raise RunSpecimenError(
            "companion TLS requires the openssl CLI on PATH "
            "(needed for --allow-lan / non-loopback binds)"
        )
    return path


def generate_ephemeral_tls(
    *,
    bind_host: str,
    destination: Path | None = None,
    days: int = 7,
) -> CompanionTLSMaterial:
    """Create a short-lived self-signed cert with SAN for the bind host."""
    openssl = _openssl_bin()
    root = Path(destination) if destination is not None else Path(tempfile.mkdtemp(prefix="rs-companion-tls-"))
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    key_path = root / "key.pem"
    cert_path = root / "cert.pem"

    san_parts = ["DNS:localhost", "IP:127.0.0.1"]
    normalized = bind_host.strip()
    try:
        addr = ipaddress.ip_address(normalized)
        san_parts.append(f"IP:{addr}")
    except ValueError:
        if normalized and normalized.lower() != "localhost":
            san_parts.append(f"DNS:{normalized}")

    # Build a config file so LibreSSL/OpenSSL both get SANs without -addext quirks.
    cfg_path = root / "openssl.cnf"
    cfg_path.write_text(
        "\n".join(
            [
                "[req]",
                "distinguished_name = req_distinguished_name",
                "x509_extensions = v3_req",
                "prompt = no",
                "[req_distinguished_name]",
                "CN = runspecimen-companion",
                "O = RunSpecimen Local Pairing",
                "[v3_req]",
                "basicConstraints = CA:FALSE",
                "keyUsage = digitalSignature, keyEncipherment",
                "extendedKeyUsage = serverAuth",
                f"subjectAltName = {','.join(san_parts)}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cmd = [
        openssl,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-days",
        str(max(1, min(days, 30))),
        "-nodes",
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-config",
        str(cfg_path),
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RunSpecimenError("openssl CLI not found for companion TLS") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RunSpecimenError(f"failed to generate companion TLS material: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RunSpecimenError("openssl timed out generating companion TLS material") from exc

    for path in (key_path, cert_path):
        try:
            path.chmod(0o600)
        except OSError:
            pass

    pem = cert_path.read_bytes()
    fp = fingerprint_sha256_of_pem(pem)
    return CompanionTLSMaterial(
        cert_path=cert_path,
        key_path=key_path,
        fingerprint_sha256=fp,
        fingerprint_sha256_compact=normalize_fingerprint(fp),
        ephemeral=True,
    )


def load_tls_material(*, cert_path: Path, key_path: Path) -> CompanionTLSMaterial:
    cert_path = cert_path.resolve()
    key_path = key_path.resolve()
    if not cert_path.is_file() or not key_path.is_file():
        raise RunSpecimenError("companion --tls-cert and --tls-key must point to existing files")
    pem = cert_path.read_bytes()
    fp = fingerprint_sha256_of_pem(pem)
    return CompanionTLSMaterial(
        cert_path=cert_path,
        key_path=key_path,
        fingerprint_sha256=fp,
        fingerprint_sha256_compact=normalize_fingerprint(fp),
        ephemeral=False,
    )


def wrap_server_socket(server: Any, material: CompanionTLSMaterial) -> None:
    """Apply TLS to an already-bound ThreadingHTTPServer socket."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(material.cert_path), keyfile=str(material.key_path))
    server.socket = context.wrap_socket(server.socket, server_side=True)


def connection_uses_tls(connection: Any) -> bool:
    return isinstance(connection, ssl.SSLSocket)


def peer_is_loopback(client_address: tuple[Any, ...] | None) -> bool:
    if not client_address:
        return False
    host = client_address[0]
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return str(host).lower() in {"localhost"}


def remote_confirm_transport_ok(*, client_address: tuple[Any, ...] | None, connection: Any) -> bool:
    """Allow remote-confirm only on loopback cleartext or any TLS connection."""
    if peer_is_loopback(client_address):
        return True
    return connection_uses_tls(connection)
