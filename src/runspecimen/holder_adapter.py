"""Unprivileged test adapter for the execution holder.

The adapter listens on a filesystem socket in a directory the test created.
It is not a launchd daemon, not an XPC service, and not a network server.
``installed_protection`` stays false. A passing test does not prove that a
same-user process cannot rewrite the holder. These tests do not prove
installed protection.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from runspecimen.execution_holder import (
    ExecutionHolder,
    HolderRefusal,
    handle_message,
    open_sealed,
    seal,
)
from runspecimen.hashutil import iter_source_files, sha256_file
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
from runspecimen.runtime import runtime_provenance

HumanFor = Callable[[str, str], dict[str, Any]]


class AdapterServer:
    def __init__(
        self,
        root: Path,
        *,
        bootstrap_secret: str,
        allow_test_double: bool = True,
        read_timeout_sec: float = DEFAULT_READ_TIMEOUT_SEC,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        max_in_flight: int = DEFAULT_MAX_IN_FLIGHT,
    ) -> None:
        self.root = Path(root)
        self.bootstrap_secret = bootstrap_secret
        self.socket_path = self.root / "holder.sock"
        self.read_timeout_sec = read_timeout_sec
        self.max_frame_bytes = max_frame_bytes
        self._admission = AdmissionGate(max_in_flight)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Explicit test-double construction. Not hardware. Not installed protection.
        self.holder = ExecutionHolder(
            self.root / "state",
            allow_test_double=allow_test_double,
            installed_protection=False,
            bootstrap_secret=bootstrap_secret,
            snapshot_base=self.root / "run-snapshots",
        )

    def start(self) -> None:
        if self.socket_path.exists():
            self.socket_path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        sock.listen(DEFAULT_ACCEPT_BACKLOG)
        sock.settimeout(0.2)
        self._sock = sock

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    conn, _addr = sock.accept()
                except TimeoutError:
                    continue
                except socket.timeout:
                    # Python 3.9 raises socket.timeout for accept deadlines.
                    continue
                except OSError:
                    if self._stop.is_set():
                        return
                    raise
                if not self._admission.try_enter():
                    try:
                        write_frame(
                            conn,
                            json.dumps(
                                {
                                    "ok": False,
                                    "error": "holder admission limit reached",
                                    "installed_protection": False,
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
                            self._one(connection)
                    finally:
                        self._admission.leave()

                threading.Thread(target=worker, args=(conn,), daemon=True).start()

        self._thread = threading.Thread(target=loop, name="holder-test-adapter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        sock = getattr(self, "_sock", None)
        if sock is not None:
            sock.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _one(self, conn: socket.socket) -> None:
        try:
            raw = read_frame(
                conn,
                max_bytes=self.max_frame_bytes,
                timeout_sec=self.read_timeout_sec,
            )
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise HolderRefusal("holder message is not an object")
            peer_uid, peer_gid = os.getuid(), os.getgid()
            try:
                if hasattr(conn, "getpeereid"):
                    peer_uid, peer_gid = conn.getpeereid()  # type: ignore[attr-defined]
            except OSError:
                pass
            response = handle_message(
                self.holder,
                message,
                bootstrap_secret=self.bootstrap_secret,
                peer_uid=int(peer_uid),
                peer_gid=int(peer_gid),
            )
        except (HolderRefusal, FrameError, json.JSONDecodeError, OSError, ValueError) as exc:
            response = {"ok": False, "error": str(exc), "installed_protection": False}
        write_frame(conn, json.dumps(response, sort_keys=True))


class HolderClient:
    """Authenticated client. The caller secret never travels inside the body."""

    def __init__(
        self,
        socket_path: Path,
        caller_id: str,
        caller_secret: str,
        human_for: HumanFor,
        *,
        key_generation: int = 1,
        expect_installed: bool = False,
        read_timeout_sec: float = DEFAULT_READ_TIMEOUT_SEC,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        device_secrets: dict[str, str] | None = None,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.caller_id = caller_id
        self.caller_secret = caller_secret
        self.human_for = human_for
        self.key_generation = key_generation
        self.expect_installed = bool(expect_installed)
        self.read_timeout_sec = read_timeout_sec
        self.max_frame_bytes = max_frame_bytes
        self.device_secrets = dict(device_secrets or {})

    def call(self, body: dict[str, Any]) -> dict[str, Any]:
        message = seal(self.caller_secret, caller_id=self.caller_id, body=body)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(self.socket_path))
            write_frame(sock, json.dumps(message, sort_keys=True))
            raw = read_frame(
                sock,
                max_bytes=self.max_frame_bytes,
                timeout_sec=self.read_timeout_sec,
            )
        finally:
            sock.close()
        response = json.loads(raw)
        if not isinstance(response, dict):
            raise HolderRefusal("holder response is not an object")
        if response.get("ok") is False:
            raise HolderRefusal(str(response.get("error") or "holder refused"))
        body_out = open_sealed(self.caller_secret, response)
        installed = bool(body_out.get("installed_protection"))
        if self.expect_installed:
            if not installed:
                raise HolderRefusal("installed holder did not claim installed protection")
        elif installed:
            raise HolderRefusal("test adapter claimed installed protection")
        if "caller_secret" in body_out and isinstance(body_out.get("caller_secret"), str):
            self.caller_secret = body_out["caller_secret"]
        if isinstance(body_out.get("key_generation"), int):
            self.key_generation = body_out["key_generation"]
        if isinstance(body_out.get("device_secret"), str) and isinstance(body_out.get("device_id"), str):
            self.device_secrets[str(body_out["device_id"])] = str(body_out["device_secret"])
        return body_out


def authorize_held_execution(contract: Any, workspace: Path, client: HolderClient) -> dict[str, Any]:
    """Ask the connected holder to consume this contract's bound snapshot.

    Consume does not spawn. ``execute_held_execution`` must follow after the
    client finishes preflight checks. The client must not Popen a held policy.
    Unprivileged tests do not prove installed protection.
    """
    policy = getattr(contract, "execution_approval", None)
    if policy not in {"local", "companion", "dual"}:
        raise HolderRefusal("held execution requires a local, companion, or dual policy")
    runtime = runtime_provenance(contract, workspace)
    executable = str(Path(str(runtime["resolved_executable"])).resolve())
    files: list[list[str]] = [[executable, sha256_file(Path(executable))]]
    seen = {executable}
    for path in iter_source_files(
        workspace,
        list(contract.source.roots),
        list(contract.source.excludes),
    ):
        abs_path = str(path.resolve())
        if abs_path in seen:
            continue
        seen.add(abs_path)
        files.append([abs_path, sha256_file(path)])
    for token in contract.argv[1:]:
        candidate = Path(token)
        if not candidate.is_absolute():
            candidate = (workspace / candidate).resolve()
        else:
            candidate = candidate.resolve()
        abs_path = str(candidate)
        if abs_path in seen or not candidate.is_file():
            continue
        try:
            candidate.relative_to(workspace.resolve())
        except ValueError:
            continue
        seen.add(abs_path)
        files.append([abs_path, sha256_file(candidate)])
    for rel in getattr(contract, "holder_reads", ()) or ():
        candidate = (workspace / str(rel)).resolve()
        abs_path = str(candidate)
        if abs_path in seen or not candidate.is_file():
            continue
        try:
            candidate.relative_to(workspace.resolve())
        except ValueError:
            continue
        seen.add(abs_path)
        files.append([abs_path, sha256_file(candidate)])
    nonce = str(contract.contract_hash)
    cwd = str((workspace / str(getattr(contract, "cwd", ".") or ".")).resolve())
    if runtime.get("interpreter"):
        launch_argv = [
            str(runtime["interpreter"]),
            *[str(x) for x in (runtime.get("interpreter_args") or [])],
            executable,
            *[str(x) for x in list(contract.argv)[1:]],
        ]
    else:
        launch_argv = [executable, *[str(x) for x in list(contract.argv)[1:]]]
    binding = {
        "contract_hash": contract.contract_hash,
        "workspace": str(workspace.resolve()),
        "argv": list(contract.argv),
        "executable": executable,
        "policy": policy,
        "cwd": cwd,
        "launch_argv": launch_argv,
        "bounds": {
            "wall_timeout_sec": contract.caps.wall_timeout_sec,
            "stdout_max_bytes": contract.caps.stdout_max_bytes,
            "stderr_max_bytes": contract.caps.stderr_max_bytes,
        },
        "key_generation": client.key_generation,
        "reads": sorted(seen),
    }
    return client.call(
        {
            "op": "consume",
            "nonce": nonce,
            "policy": policy,
            "human": client.human_for("consume", nonce),
            "workspace": str(workspace.resolve()),
            "files": files,
            "binding": binding,
        }
    )


def execute_held_execution(contract: Any, workspace: Path, client: HolderClient, receipt: dict[str, Any]) -> dict[str, Any]:
    """Holder-owned spawn and completion for a consumed nonce."""
    policy = getattr(contract, "execution_approval", None)
    if policy not in {"local", "companion", "dual"}:
        raise HolderRefusal("held execution requires a local, companion, or dual policy")
    nonce = str(receipt.get("nonce") or contract.contract_hash)
    executed = client.call(
        {
            "op": "execute",
            "token": nonce,
            "human": client.human_for("execute", nonce),
        }
    )
    merged = dict(receipt)
    merged.update(
        {
            "exit_code": executed.get("exit_code"),
            "timed_out": executed.get("timed_out"),
            "stdout_b64": executed.get("stdout_b64"),
            "stderr_b64": executed.get("stderr_b64"),
            "stdout_truncated": executed.get("stdout_truncated"),
            "stderr_truncated": executed.get("stderr_truncated"),
            "executed": True,
            "supervisor": "holder",
        }
    )
    return merged


def rewrite_launch_from_snapshots(
    launch_argv: list[str],
    *,
    path_map: dict[str, str],
    workspace: Path,
    live_executable: str | None = None,
) -> list[str]:
    """Replace workspace input paths with snapshotted inodes from consume.

    A system interpreter outside the workspace may stay live. A workspace
    executable must come from the snapshot map and is never exempted by
    ``live_executable``. Unprivileged tests do not prove installed protection.
    """
    if not path_map:
        raise HolderRefusal("held launch has no snapshot path map")
    rewritten: list[str] = []
    ws = workspace.resolve()
    for index, token in enumerate(launch_argv):
        candidate = Path(token)
        resolved: Path | None = None
        try:
            if candidate.is_absolute():
                resolved = candidate.resolve()
            else:
                resolved = (ws / candidate).resolve()
        except OSError:
            resolved = None
        in_workspace = False
        if resolved is not None:
            try:
                resolved.relative_to(ws)
                in_workspace = True
            except ValueError:
                in_workspace = False
        if (
            index == 0
            and live_executable is not None
            and not in_workspace
            and resolved is not None
            and str(resolved) == str(Path(live_executable).resolve())
        ):
            rewritten.append(str(resolved))
            continue
        if resolved is not None and str(resolved) in path_map:
            if in_workspace:
                rewritten.append(path_map[str(resolved)])
            else:
                rewritten.append(str(resolved))
        else:
            if in_workspace and resolved is not None and resolved.is_file():
                raise HolderRefusal(
                    f"workspace path {resolved} was not snapshotted for held launch"
                )
            rewritten.append(token)
    if not rewritten:
        raise HolderRefusal("held launch argv is empty")
    return rewritten


INSTALLED_SUPPORT_DIR = Path(
    "/Library/Application Support/com.darashkevich.runspecimen.holder"
)
INSTALLED_SOCKET_NAME = "holder.sock"


def installed_socket_path() -> Path:
    return INSTALLED_SUPPORT_DIR / INSTALLED_SOCKET_NAME


def discover_installed_holder_client(
    caller_id: str,
    caller_secret: str,
    human_for: HumanFor,
    *,
    key_generation: int = 1,
) -> HolderClient | None:
    """Return a client for the root SMAppService daemon socket if it exists.

    Presence of the socket is not proof of protection. The daemon must answer
    with ``installed_protection`` true, and the state directory must be
    root-owned. Administrator or root can still defeat the holder. This helper
    does not prove installed protection by itself.
    """
    path = installed_socket_path()
    if not path.is_socket() and not path.exists():
        return None
    return HolderClient(
        path,
        caller_id,
        caller_secret,
        human_for,
        key_generation=key_generation,
        expect_installed=True,
    )
