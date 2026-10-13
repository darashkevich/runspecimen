#!/usr/bin/env python3
"""Privilege-dropping exec helper for holder payloads.

Runs as its own single-threaded process. The threaded holder daemon must not
use ``preexec_fn``; it launches this helper instead. The helper clears
supplementary groups (fail closed), drops to a non-root uid/gid, then execs
the payload. Unprivileged tests do not prove installed protection.
"""

from __future__ import annotations

import argparse
import os
import sys


def _die(message: str, code: int = 2) -> None:
    print(f"holder-drop-exec: {message}", file=sys.stderr)
    raise SystemExit(code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="holder-drop-exec")
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--gid", type=int, required=True)
    parser.add_argument("--cwd", type=str, required=True)
    parser.add_argument("payload", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    payload = list(args.payload)
    if payload and payload[0] == "--":
        payload = payload[1:]
    if not payload:
        _die("payload argv is missing")
    uid = int(args.uid)
    gid = int(args.gid)
    if uid == 0 or gid < 0:
        _die("payload identity must be a non-root uid")
    if os.geteuid() == 0:
        try:
            os.setgid(gid)
        except OSError as exc:
            _die(f"setgid failed: {exc}")
        try:
            os.setgroups([])
        except OSError as exc:
            _die(f"setgroups failed: {exc}")
        try:
            os.setuid(uid)
        except OSError as exc:
            _die(f"setuid failed: {exc}")
    else:
        # Unprivileged harness: refuse to claim a drop we cannot perform.
        if os.getuid() != uid or os.getgid() != gid:
            _die("unprivileged helper cannot change to a different payload identity")
    if os.getuid() == 0:
        _die("payload identity is still root after drop")
    try:
        os.chdir(args.cwd)
    except OSError as exc:
        _die(f"chdir failed: {exc}")
    os.environ.pop("PYTHONPATH", None)
    os.environ.pop("PYTHONHOME", None)
    os.environ.pop("PYTHONUSERBASE", None)
    os.environ.pop("RS_HOLDER_PYTHON", None)
    os.environ.pop("RS_HOLDER_BOOTSTRAP_SECRET", None)
    os.environ.pop("RS_HOLDER_MODULE_ROOT", None)
    try:
        os.execvp(payload[0], payload)
    except OSError as exc:
        _die(f"exec failed: {exc}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
