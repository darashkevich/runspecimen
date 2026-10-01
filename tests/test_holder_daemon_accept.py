"""Unit tests for holder_daemon accept-loop timeout handling.

Exercises a private UNIX socket only. Does not touch the live
``/Library/.../holder.sock`` or reinstall Holder.app.
"""

from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from runspecimen.holder_daemon import ACCEPT_TIMEOUT_SEC, _accept_connection


class HolderDaemonAcceptTimeoutTests(unittest.TestCase):
    def test_accept_returns_none_on_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.sock"
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(sock.close)
            sock.bind(str(path))
            sock.listen(1)
            sock.settimeout(ACCEPT_TIMEOUT_SEC)
            started = time.monotonic()
            result = _accept_connection(sock)
            elapsed = time.monotonic() - started
            self.assertIsNone(result)
            self.assertGreaterEqual(elapsed, ACCEPT_TIMEOUT_SEC * 0.5)
            self.assertLess(elapsed, 2.0)

    def test_accept_returns_connected_socket(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.sock"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(server.close)
            server.bind(str(path))
            server.listen(1)
            server.settimeout(ACCEPT_TIMEOUT_SEC)

            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(client.close)

            def _connect() -> None:
                time.sleep(0.05)
                client.connect(str(path))

            threading.Thread(target=_connect, daemon=True).start()
            conn = _accept_connection(server)
            self.assertIsNotNone(conn)
            assert conn is not None
            self.addCleanup(conn.close)

    def test_python39_accept_raises_socket_timeout_not_timeout_error(self) -> None:
        """Document 3.9 semantics: timed-out accept raises socket.timeout."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.sock"
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(sock.close)
            sock.bind(str(path))
            sock.listen(1)
            sock.settimeout(0.05)
            with self.assertRaises(socket.timeout):
                sock.accept()
            # On 3.9 socket.timeout is not TimeoutError; on 3.10+ it may be.
            if socket.timeout is not TimeoutError:
                self.assertFalse(issubclass(socket.timeout, TimeoutError))

    def test_non_timeout_accept_error_propagates(self) -> None:
        class _Raising:
            def accept(self) -> None:
                raise OSError(53, "accept failed")

        with self.assertRaises(OSError) as caught:
            _accept_connection(_Raising())  # type: ignore[arg-type]
        self.assertNotIsInstance(caught.exception, socket.timeout)
        if socket.timeout is not TimeoutError:
            self.assertNotIsInstance(caught.exception, TimeoutError)

    def test_repeated_timeout_then_successful_connection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.sock"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(server.close)
            server.bind(str(path))
            server.listen(1)
            server.settimeout(0.05)
            self.assertIsNone(_accept_connection(server))

            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(client.close)
            # Queue the client before accept. A sleep inside the accept window
            # races on a slow macOS runner and looks like another timeout.
            client.connect(str(path))
            conn = _accept_connection(server)
            self.assertIsNotNone(conn)
            assert conn is not None
            self.addCleanup(conn.close)


if __name__ == "__main__":
    unittest.main()
