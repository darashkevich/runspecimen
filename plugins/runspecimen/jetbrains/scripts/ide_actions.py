#!/usr/bin/env python3
"""JetBrains / IDE action router — shells to the shared adapter; no approve.

Maps UI / Junie-facing action names onto ``runspecimen_adapter.py``. Intentionally
excludes ``approve`` and remote-confirm settle so an in-IDE button cannot bypass
the human TTY gate.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ADAPTER = SCRIPT_DIR.parents[1] / "scripts" / "runspecimen_adapter.py"

# IDE-facing names → adapter action (or a special handoff for request-approval).
ALLOWED_ACTIONS = frozenset({
    "about",
    "doctor",
    "validate",
    "status",
    "preflight",
    "run",
    "postflight",
    "verify",
    "dashboard",
    "request-approval",
})


def approval_handoff(workspace: Path, contract: Path) -> str:
    return (
        "Human TTY approval required. Run this in a real terminal "
        "(do not type APPROVE from an agent or IDE auto-confirm):\n\n"
        f"runspecimen approve --workspace {workspace.resolve()} "
        f"--contract {contract.resolve()}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RunSpecimen IDE actions (approve intentionally excluded)",
    )
    parser.add_argument("action", choices=sorted(ALLOWED_ACTIONS))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--campaign-id")
    parser.add_argument("--run-id")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)

    if args.action == "request-approval":
        if args.workspace is None or args.contract is None:
            parser.error("request-approval requires --workspace and --contract")
        sys.stdout.write(approval_handoff(args.workspace, args.contract))
        return 0

    if not ADAPTER.is_file():
        parser.error(f"adapter missing: {ADAPTER}")

    command = [sys.executable, str(ADAPTER), args.action]
    if args.workspace is not None:
        command.extend(["--workspace", str(args.workspace)])
    if args.contract is not None:
        command.extend(["--contract", str(args.contract)])
    if args.campaign_id is not None:
        command.extend(["--campaign-id", args.campaign_id])
    if args.run_id is not None:
        command.extend(["--run-id", args.run_id])
    if args.open:
        command.append("--open")
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
