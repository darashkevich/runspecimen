"""Root-installed execution holder daemon.

This process is meant to run as root under SMAppService.daemon. It owns a
mode-0700 state directory under /Library/Application Support and serves the
same authenticated AF_UNIX protocol as the unprivileged test adapter.

``allow_test_double`` is off. ``installed_protection`` is on. A software test
double is refused. An imported secure-enclave label is not attestation.
Administrator or root can still defeat this holder.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import sys
from pathlib import Path

from runspecimen.execution_holder import ExecutionHolder, HolderRefusal, handle_message
from runspecimen.holder_adapter import INSTALLED_SUPPORT_DIR, INSTALLED_SOCKET_NAME

BOOTSTRAP_ENV = "RS_HOLDER_BOOTSTRAP_SECRET"


def _ensure_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("holder daemon must run as root")


def _prepare_dirs(support: Path) -> tuple[Path, Path]:
    support.mkdir(parents=True, exist_ok=True)
    os.chmod(support, 0o755)
    state = support / "state"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    # Socket lives beside state so clients can traverse support (755) but cannot
    # rewrite enrollment, policy, nonces, or leases under state (700).
    sock_path = support / INSTALLED_SOCKET_NAME
    return state, sock_path


def _read_line(conn: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        piece = conn.recv(65536)
        if not piece:
            break
        chunks.append(piece)
        if b"\n" in piece:
            break
    text = b"".join(chunks).decode("utf-8")
    if not text.endswith("\n"):
        raise HolderRefusal("holder connection closed before a message")
    return text


def _write_line(conn: socket.socket, text: str) -> None:
    conn.sendall(text.encode("utf-8") + b"\n")


def serve(support: Path, *, bootstrap_secret: str) -> int:
    _ensure_root()
    state, sock_path = _prepare_dirs(support)
    holder = ExecutionHolder(state, allow_test_double=False, installed_protection=True)
    if sock_path.exists():
        sock_path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))
    # Authenticated protocol; world may connect, same-user cannot rewrite state.
    os.chmod(sock_path, 0o666)
    sock.listen(8)
    while True:
        conn, _addr = sock.accept()
        with conn:
            try:
                raw = _read_line(conn)
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise HolderRefusal("holder message is not an object")
                response = handle_message(
                    holder,
                    message,
                    bootstrap_secret=bootstrap_secret,
                )
            except (HolderRefusal, json.JSONDecodeError, OSError, ValueError) as exc:
                response = {
                    "ok": False,
                    "error": str(exc),
                    "installed_protection": True,
                }
            _write_line(conn, json.dumps(response, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runspecimen-holder-daemon")
    parser.add_argument(
        "--support-dir",
        type=Path,
        default=INSTALLED_SUPPORT_DIR,
        help="root-owned support directory containing state/ and holder.sock",
    )
    args = parser.parse_args(argv)
    secret = os.environ.get(BOOTSTRAP_ENV, "").strip()
    if len(secret) < 32:
        print("RS_HOLDER_BOOTSTRAP_SECRET missing or too short", file=sys.stderr)
        return 2
    return serve(args.support_dir, bootstrap_secret=secret)


if __name__ == "__main__":
    raise SystemExit(main())
