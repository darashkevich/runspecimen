"""Detached supervisor for approved CLI runs.

When `runspecimen run` executes an approved contract, the supervisor process
(not the presentation CLI) owns the lease, deadline enforcement, and cleanup.

Design rationale:
- SIGKILL of the CLI cannot be caught by that CLI
- A separate session keeps the supervisor alive when the CLI's group dies
- The control pipe detects CLI death via EOF
- Wall deadline is enforced even if the CLI is stopped (SIGSTOP)
- No workload inherits the control channel

What the supervisor guarantees:
- The contract will be killed at wall_timeout_sec, regardless of CLI state
- Lease is held until cleanup is confirmed
- State accurately reports cleanup_confirmed status

What it cannot guarantee:
- SIGKILL of BOTH the CLI AND supervisor still orphans the contract
- In that case, status will show phase=running or cleanup_pending, which is
  correct (cleanup was not confirmed)
"""
from __future__ import annotations

import os
import signal
import sys
import threading
import time
from multiprocessing.connection import Pipe
from pathlib import Path
from typing import Any

from runspecimen import errors


def guarded_run(
    *,
    contract_path: Path,
    workspace: Path,
    now: float | None = None,
) -> dict[str, Any]:
    """Execute an approved contract under a detached supervisor.

    The supervisor:
    1. Runs in its own session (setsid)
    2. Detaches stdin/stdout/stderr (uses /dev/null)
    3. Watches a control pipe from the CLI
    4. Owns the lease, deadline, and cleanup

    The CLI receives results via IPC pipe, not stdout.
    """
    from runspecimen import run as execution

    # Create communication channels
    result_reader, result_writer = Pipe(duplex=False)
    control_reader_fd, control_writer_fd = os.pipe()

    try:
        pid = os.fork()
    except BaseException:
        result_reader.close()
        result_writer.close()
        os.close(control_reader_fd)
        os.close(control_writer_fd)
        raise

    if pid == 0:
        # === CHILD: the supervisor ===
        result_reader.close()
        os.close(control_writer_fd)

        try:
            # New session - survives parent group death
            os.setsid()

            # Detach stdio - don't hold CLI's console during cleanup
            null_fd = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null_fd, fd)
            if null_fd > 2:
                os.close(null_fd)

            # Watch for CLI death via control pipe EOF
            cli_lost = threading.Event()
            execution._external_interrupt = cli_lost

            def watch_control_pipe():
                try:
                    # Block until: stop byte received OR pipe closed (CLI died)
                    os.read(control_reader_fd, 1)
                finally:
                    cli_lost.set()
                    try:
                        os.close(control_reader_fd)
                    except OSError:
                        pass

            watcher = threading.Thread(target=watch_control_pipe, daemon=True)
            watcher.start()

            # Notification callback for cleanup_pending
            notified = False

            def notify_cleanup_pending(message: str) -> None:
                nonlocal notified
                if not notified:
                    notified = True
                    try:
                        result_writer.send(("error", "RunError", message))
                    except (BrokenPipeError, EOFError, OSError):
                        pass

            execution._cleanup_notification = notify_cleanup_pending

            # Run the contract
            try:
                result = execution.run_contract(
                    contract_path=contract_path,
                    workspace=workspace,
                    now=now,
                )
                payload = ("ok", result)
            except BaseException as exc:
                payload = ("error", type(exc).__name__, str(exc))

            # Send result (only if not already sent via cleanup_pending)
            if not notified:
                try:
                    result_writer.send(payload)
                except (BrokenPipeError, EOFError, OSError):
                    pass

        finally:
            result_writer.close()
            os._exit(0)

    # === PARENT: the CLI ===
    result_writer.close()
    os.close(control_reader_fd)
    stop_sent = False

    try:
        with execution._termination_signals():
            # Poll for result, forwarding termination signals
            while not result_reader.poll(0.1):
                pending = execution._pending_signal.get()
                if pending and not stop_sent:
                    # Forward stop request to supervisor
                    try:
                        os.write(control_writer_fd, b"s")
                    except (BrokenPipeError, OSError):
                        pass
                    stop_sent = True

            # Get result from supervisor
            try:
                payload = result_reader.recv()
            except EOFError:
                raise errors.RunError(
                    "Supervisor exited without result; cleanup status is unknown. "
                    "Check `runspecimen status` - if phase is cleanup_pending, "
                    "the lease is retained until cleanup succeeds."
                )

        # Interpret result
        if payload[0] == "ok":
            return payload[1]

        # Map error type
        exc_name = payload[1]
        exc_msg = payload[2]

        if exc_name in ("_RunInterrupted", "KeyboardInterrupt"):
            raise KeyboardInterrupt()

        exc_cls = getattr(errors, exc_name, None)
        if exc_cls is None or not isinstance(exc_cls, type) or not issubclass(exc_cls, errors.RunSpecimenError):
            exc_cls = errors.RunError

        raise exc_cls(exc_msg)

    finally:
        result_reader.close()
        try:
            os.close(control_writer_fd)
        except OSError:
            pass

        # Reap supervisor if it already exited, but don't wait if it's
        # handling cleanup_pending (it needs to stay alive with the lease)
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
