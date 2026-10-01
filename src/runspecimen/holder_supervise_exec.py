#!/usr/bin/env python3
"""Hold a payload until the holder arms supervision, then exec it.

The holder writes one byte to the gate fd only after the watch is registered.
This process must not fork before that read. It is not a Secure Enclave and
it does not prove installed protection.
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[1] != "--":
        print("holder-supervise-exec: usage gate_fd -- argv", file=sys.stderr)
        return 2
    try:
        gate = int(args[0])
    except ValueError:
        print("holder-supervise-exec: gate fd is not an integer", file=sys.stderr)
        return 2
    payload = args[2:]
    if not payload:
        print("holder-supervise-exec: payload argv is missing", file=sys.stderr)
        return 2
    try:
        os.read(gate, 1)
    except OSError as exc:
        print(f"holder-supervise-exec: gate read failed: {exc}", file=sys.stderr)
        return 2
    try:
        os.close(gate)
    except OSError:
        pass
    os.execv(payload[0], payload)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
