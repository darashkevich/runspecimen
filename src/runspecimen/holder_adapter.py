"""Unprivileged test adapter for the execution holder.

The adapter listens on a filesystem socket in a directory the test created.
It is not a launchd daemon, not an XPC service, and not a network server.
``installed_protection`` stays false. A passing test does not prove that a
same-user process cannot rewrite the holder.
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
from runspecimen.runtime import runtime_provenance

HumanFor = Callable[[str, str], dict[str, Any]]


class AdapterServer:
    def __init__(self, root: Path, *, bootstrap_secret: str) -> None:
        self.root = Path(root)
        self.bootstrap_secret = bootstrap_secret
        self.socket_path = self.root / "holder.sock"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.holder = ExecutionHolder(self.root / "state", allow_test_double=True)

    def start(self) -> None:
        if self.socket_path.exists():
            self.socket_path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        sock.listen(4)
        sock.settimeout(0.2)
        self._sock = sock

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    conn, _addr = sock.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        return
                    raise
                with conn:
                    self._one(conn)

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
            raw = _read_line(conn)
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise HolderRefusal("holder message is not an object")
            response = handle_message(
                self.holder,
                message,
                bootstrap_secret=self.bootstrap_secret,
            )
        except (HolderRefusal, json.JSONDecodeError, OSError, ValueError) as exc:
            response = {"ok": False, "error": str(exc), "installed_protection": False}
        _write_line(conn, json.dumps(response, sort_keys=True))


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
    ) -> None:
        self.socket_path = Path(socket_path)
        self.caller_id = caller_id
        self.caller_secret = caller_secret
        self.human_for = human_for
        self.key_generation = key_generation
        self.expect_installed = bool(expect_installed)

    def call(self, body: dict[str, Any]) -> dict[str, Any]:
        message = seal(self.caller_secret, caller_id=self.caller_id, body=body)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(self.socket_path))
            _write_line(sock, json.dumps(message, sort_keys=True))
            raw = _read_line(sock)
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
        return body_out


def authorize_held_execution(contract: Any, workspace: Path, client: HolderClient) -> dict[str, Any]:
    """Ask the connected holder to consume this contract's bound snapshot.

    The holder re-reads the files. A digest that does not match is a refusal,
    and this function does not spawn the contract. The returned ``path_map``
    names snapshot inodes that the run path must exec and read.
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
    nonce = str(contract.contract_hash)
    binding = {
        "contract_hash": contract.contract_hash,
        "workspace": str(workspace.resolve()),
        "argv": list(contract.argv),
        "executable": executable,
        "policy": policy,
        "bounds": {
            "wall_timeout_sec": contract.caps.wall_timeout_sec,
            "stdout_max_bytes": contract.caps.stdout_max_bytes,
            "stderr_max_bytes": contract.caps.stderr_max_bytes,
        },
        "key_generation": client.key_generation,
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


def rewrite_launch_from_snapshots(
    launch_argv: list[str],
    *,
    path_map: dict[str, str],
    workspace: Path,
    live_executable: str | None = None,
) -> list[str]:
    """Replace workspace input paths with snapshotted inodes from consume.

    A system interpreter outside the workspace stays live. Its digest was bound
    at consume; the dynamic linker residual remains. Workspace scripts and
    inputs must come from the snapshot map.
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
        if index == 0 and live_executable is not None:
            live = str(Path(live_executable).resolve())
            if resolved is not None and str(resolved) == live:
                rewritten.append(live)
                continue
        if resolved is not None and str(resolved) in path_map:
            try:
                resolved.relative_to(ws)
            except ValueError:
                # Outside the workspace: keep the live path; the digest was bound.
                rewritten.append(str(resolved))
                continue
            rewritten.append(path_map[str(resolved)])
        else:
            rewritten.append(token)
    if not rewritten:
        raise HolderRefusal("held launch argv is empty")
    return rewritten


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
    root-owned. Administrator or root can still defeat the holder.
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
