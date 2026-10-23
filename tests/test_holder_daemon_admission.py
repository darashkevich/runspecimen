"""Exercise the installed daemon's actual accept/worker loop on private sockets."""
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from runspecimen import holder_daemon as daemon
from runspecimen.holder_io import read_frame, write_frame


class DaemonAdmissionTests(unittest.TestCase):
    def test_real_serve_loop_refuses_busy_then_releases_after_read_deadline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / 'holder.sock'
            entered = threading.Event()
            released = threading.Event()
            stopping = threading.Event()
            listening = threading.Event()
            errors = []
            sockets = []
            real_socket = socket.socket
            real_accept = daemon._accept_connection
            real_read = daemon.read_frame
            real_gate = daemon.AdmissionGate

            class StopServe(Exception):
                pass

            class Gate(real_gate):
                def leave(self):
                    super().leave()
                    released.set()

            def accept(sock):
                listening.set()
                if stopping.is_set():
                    raise StopServe()
                return real_accept(sock)

            def read(conn, **kwargs):
                self.assertEqual(kwargs['timeout_sec'], 0.2)
                entered.set()
                return real_read(conn, **kwargs)

            def make_socket(*args, **kwargs):
                sock = real_socket(*args, **kwargs)
                sockets.append(sock)
                return sock

            def run():
                try:
                    daemon.serve(root, bootstrap_secret='fixture-only')
                except StopServe:
                    pass
                except BaseException as exc:
                    errors.append(exc)

            # Only installation/identity and message dispatch boundaries are
            # fixtures. Admission, framing, deadlines and worker cleanup are real.
            with mock.patch.object(daemon, '_ensure_root'), \
                 mock.patch.object(daemon, 'refuse_user_python_injection'), \
                 mock.patch.object(daemon, '_prepare_dirs', return_value=(root, root, path)), \
                 mock.patch.object(daemon, 'ExecutionHolder'), \
                 mock.patch.object(daemon, '_peer_ids', return_value=(501, 20)), \
                 mock.patch.object(daemon, 'handle_message', return_value={'ok': True}), \
                 mock.patch.object(daemon, 'DEFAULT_MAX_IN_FLIGHT', 1), \
                 mock.patch.object(daemon, 'DEFAULT_READ_TIMEOUT_SEC', 0.2), \
                 mock.patch.object(daemon, 'ACCEPT_TIMEOUT_SEC', 0.05), \
                 mock.patch.object(daemon, 'AdmissionGate', Gate), \
                 mock.patch.object(daemon, '_accept_connection', side_effect=accept), \
                 mock.patch.object(daemon, 'read_frame', side_effect=read), \
                 mock.patch.object(daemon.socket, 'socket', side_effect=make_socket):
                thread = threading.Thread(target=run, daemon=True)
                thread.start()
                try:
                    self.assertTrue(listening.wait(5))
                    with real_socket(socket.AF_UNIX, socket.SOCK_STREAM) as first:
                        first.connect(str(path))
                        self.assertTrue(entered.wait(5))
                        with real_socket(socket.AF_UNIX, socket.SOCK_STREAM) as second:
                            second.connect(str(path))
                            refused = json.loads(read_frame(second, timeout_sec=5))
                            self.assertIn('admission limit reached', refused['error'])
                        self.assertTrue(released.wait(5), 'real worker must release after deadline')
                    with real_socket(socket.AF_UNIX, socket.SOCK_STREAM) as third:
                        third.connect(str(path))
                        write_frame(third, '{}')
                        self.assertTrue(json.loads(read_frame(third, timeout_sec=5))['ok'])
                finally:
                    stopping.set()
                    thread.join(5)
                    for sock in sockets:
                        sock.close()
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])
