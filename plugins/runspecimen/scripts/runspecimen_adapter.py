#!/usr/bin/env python3
"""Narrow adapter for agent hosts; interactive approval intentionally excluded."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ALLOWED = frozenset({"doctor", "validate", "status", "preflight", "run", "postflight", "verify"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=sorted(ALLOWED))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--campaign-id")
    parser.add_argument("--run-id")
    args = parser.parse_args()

    executable = shutil.which("runspecimen")
    if executable is None:
        parser.error("runspecimen is not installed on PATH")
    command = [executable, args.action, "--workspace", str(args.workspace.resolve())]
    if args.contract is not None:
        command.extend(["--contract", str(args.contract.resolve())])
    if args.campaign_id is not None:
        command.extend(["--campaign-id", args.campaign_id])
    if args.run_id is not None:
        command.extend(["--run-id", args.run_id])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
