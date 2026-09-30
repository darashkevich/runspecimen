"""Root-installed execution holder daemon source.

This module is the daemon source tree only. This pass does not modify, restart,
or exercise any installed root daemon. ``allow_test_double`` is off.
``installed_protection`` is on. A software test double is refused. An imported
secure-enclave label is not attestation. Administrator or root can still defeat
this holder. Unprivileged tests do not prove installed protection.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
from pathlib import Path

from runspecimen.execution_holder import ExecutionHolder, HolderRefusal, handle_message
from runspecimen.holder_adapter import INSTALLED_SOCKET_NAME, INSTALLED_SUPPORT_DIR
from runspecimen.holder_runtime import (
    RuntimeTrustError,
    assert_module_root,
    refuse_user_python_injection,
)

from runspecimen.holder_io import (
    DEFAULT_ACCEPT_BACKLOG,
    DEFAULT_MAX_IN_FLIGHT,
    DEFAULT_READ_TIMEOUT_SEC,
    MAX_FRAME_BYTES,
    AdmissionGate,
    FrameError,
    read_frame,
    write_frame,
)

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
    sock_path = support / INSTALLED_SOCKET_NAME
    return state, sock_path


def serve(support: Path, *, bootstrap_secret: str) -> int:
    _ensure_root()
    try:
        refuse_user_python_injection()
        module_root = os.environ.get("RS_HOLDER_MODULE_ROOT")
        if module_root:
            assert_module_root(Path(module_root))
    except RuntimeTrustError as exc:
        raise SystemExit(str(exc)) from exc
    state, sock_path = _prepare_dirs(support)
    holder = ExecutionHolder(
        state,
        allow_test_double=False,
        installed_protection=True,
        bootstrap_secret=bootstrap_secret,
    )
    if sock_path.exists():
        sock_path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))
    # Authenticated protocol; world may connect, same-user cannot rewrite state.
    # Framing/admission bounds still apply. This source change is not an install.
    os.chmod(sock_path, 0o666)
    sock.listen(DEFAULT_ACCEPT_BACKLOG)
    admission = AdmissionGate(DEFAULT_MAX_IN_FLIGHT)
    while True:
        conn, _addr = sock.accept()
        if not admission.try_enter():
            try:
                write_frame(
                    conn,
                    json.dumps(
                        {
                            "ok": False,
                            "error": "holder admission limit reached",
                            "installed_protection": True,
                        },
                        sort_keys=True,
                    ),
                )
            except OSError:
                pass
            conn.close()
            continue
        def worker(connection: socket.socket) -> None:
            try:
                with connection:
                    try:
                        raw = read_frame(
                            connection,
                            max_bytes=MAX_FRAME_BYTES,
                            timeout_sec=DEFAULT_READ_TIMEOUT_SEC,
                        )
                        message = json.loads(raw)
                        if not isinstance(message, dict):
                            raise HolderRefusal("holder message is not an object")
                        response = handle_message(
                            holder,
                            message,
                            bootstrap_secret=bootstrap_secret,
                        )
                    except (HolderRefusal, FrameError, json.JSONDecodeError, OSError, ValueError) as exc:
                        response = {
                            "ok": False,
                            "error": str(exc),
                            "installed_protection": True,
                        }
                    write_frame(connection, json.dumps(response, sort_keys=True))
            finally:
                admission.leave()

        threading.Thread(target=worker, args=(conn,), daemon=True).start()


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
