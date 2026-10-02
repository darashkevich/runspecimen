"""Root-installed execution holder daemon source.

This module is the daemon source tree only. This pass does not modify, restart,
or exercise any installed root daemon. ``allow_test_double`` is off.
``installed_protection`` is on. A software test double is refused. An imported
secure-enclave label is not attestation. Administrator or root can still defeat
this holder. Unprivileged tests do not prove installed protection.

The live process must be started via ``holder_entry.py`` (path execution), not
``python -m``, so module discovery does not depend on post-import env mutation.
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
from runspecimen.holder_runtime import RuntimeTrustError, refuse_user_python_injection

BOOTSTRAP_ENV = "RS_HOLDER_BOOTSTRAP_SECRET"
ACCEPT_TIMEOUT_SEC = 0.2


def _ensure_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("holder daemon must run as root")



def _accept_connection(sock: socket.socket) -> socket.socket | None:
    """Accept one connection, or None when the accept deadline fires.

    Python 3.9 raises socket.timeout. Python 3.10+ may raise TimeoutError.
    Any other accept error propagates. This loop has no shutdown flag.
    """
    try:
        conn, _addr = sock.accept()
    except TimeoutError:
        return None
    except socket.timeout:
        return None
    return conn


def _peer_ids(conn: socket.socket) -> tuple[int, int]:
    """Authenticated peer credentials from the connected AF_UNIX socket."""
    try:
        if hasattr(conn, "getpeereid"):
            uid, gid = conn.getpeereid()  # type: ignore[attr-defined]
            return int(uid), int(gid)
    except OSError:
        pass
    # macOS / some BSDs
    try:
        import struct

        LOCAL_PEERCRED = getattr(socket, "LOCAL_PEERCRED", 0x200000108)
        data = conn.getsockopt(0, LOCAL_PEERCRED, 24)  # SOL_LOCAL ≈ 0 on Darwin for this
        # fallback via ctypes getpeereid
    except OSError:
        data = b""
    try:
        import ctypes
        import ctypes.util

        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        uid = ctypes.c_uint()
        gid = ctypes.c_uint()
        rc = libc.getpeereid(conn.fileno(), ctypes.byref(uid), ctypes.byref(gid))
        if rc == 0:
            return int(uid.value), int(gid.value)
    except (OSError, AttributeError, ValueError):
        pass
    raise HolderRefusal("authenticated peer identity is unavailable")


def _prepare_dirs(support: Path) -> tuple[Path, Path, Path]:
    support.mkdir(parents=True, exist_ok=True)
    os.chmod(support, 0o755)
    state = support / "state"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    snapshots = support / "run-snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    os.chmod(snapshots, 0o711)
    sock_path = support / INSTALLED_SOCKET_NAME
    return state, snapshots, sock_path


def serve(support: Path, *, bootstrap_secret: str) -> int:
    _ensure_root()
    try:
        refuse_user_python_injection()
    except RuntimeTrustError as exc:
        raise SystemExit(str(exc)) from exc
    state, snapshots, sock_path = _prepare_dirs(support)
    holder = ExecutionHolder(
        state,
        allow_test_double=False,
        installed_protection=True,
        bootstrap_secret=bootstrap_secret,
        snapshot_base=snapshots,
    )
    if sock_path.exists():
        sock_path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(sock_path))
    os.chmod(sock_path, 0o666)
    sock.listen(DEFAULT_ACCEPT_BACKLOG)
    sock.settimeout(ACCEPT_TIMEOUT_SEC)
    admission = AdmissionGate(DEFAULT_MAX_IN_FLIGHT)
    while True:
        conn = _accept_connection(sock)
        if conn is None:
            continue
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
                        peer_uid, peer_gid = _peer_ids(connection)
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
                            peer_uid=peer_uid,
                            peer_gid=peer_gid,
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


def assert_support_before_secret(support: Path, env: dict[str, str] | None = None) -> None:
    """Check ancestors that already exist before a secret is read or created.

    A missing tail may be created later. A symlink or a non-sticky
    world-writable component fails closed. This is an ordering check, not a
    claim that the live daemon was exploited.
    """

    import stat

    from runspecimen.holder_runtime import RuntimeTrustError, refuse_user_python_injection

    refuse_user_python_injection(env)
    path = Path(support)
    if path.is_symlink():
        raise RuntimeTrustError(f"support path contains a symlink: {path}")
    if not path.is_absolute():
        path = Path(os.path.realpath(path))
    else:
        path = Path(os.path.realpath(path))
    cursor = Path("/")
    for part in path.parts[1:]:
        cursor = cursor / part
        if not cursor.exists() and not cursor.is_symlink():
            return
        st = os.lstat(cursor)
        if stat.S_ISLNK(st.st_mode):
            raise RuntimeTrustError(f"support path contains a symlink: {cursor}")
        mode = stat.S_IMODE(st.st_mode)
        if mode & stat.S_IWOTH:
            sticky = bool(st.st_mode & stat.S_ISVTX) and stat.S_ISDIR(st.st_mode)
            if not sticky:
                raise RuntimeTrustError(f"support path is world-writable: {cursor}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runspecimen-holder-daemon")
    parser.add_argument(
        "--support-dir",
        type=Path,
        default=INSTALLED_SUPPORT_DIR,
        help="root-owned support directory containing state/ and holder.sock",
    )
    args = parser.parse_args(argv)
    try:
        assert_support_before_secret(args.support_dir)
    except RuntimeTrustError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    secret = os.environ.get(BOOTSTRAP_ENV, "").strip()
    if len(secret) < 32:
        print("RS_HOLDER_BOOTSTRAP_SECRET missing or too short", file=sys.stderr)
        return 2
    return serve(args.support_dir, bootstrap_secret=secret)


if __name__ == "__main__":
    raise SystemExit(main())
