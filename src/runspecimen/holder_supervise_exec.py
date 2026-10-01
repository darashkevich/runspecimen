#!/usr/bin/env python3
"""Hold a payload until the holder arms supervision, then exec it.

The holder writes one byte to the gate fd only after the watch is registered.
This process must not fork before that read. It is not a Secure Enclave and
it does not prove installed protection.
"""

from __future__ import annotations

import os
import sys

# The holder writes this single byte only after supervision is armed.
# Any other result, including EOF when the holder dies, is not permission.
GO_BYTE = b"\0"


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
        got = os.read(gate, 1)
    except OSError as exc:
        print(f"holder-supervise-exec: gate read failed: {exc}", file=sys.stderr)
        return 2
    if got != GO_BYTE:
        if got == b"":
            print("holder-supervise-exec: gate closed without the go byte", file=sys.stderr)
        else:
            print("holder-supervise-exec: unexpected gate byte", file=sys.stderr)
        return 2
    try:
        os.close(gate)
    except OSError:
        pass
    if not payload[0] or not os.path.isabs(payload[0]):
        print("holder-supervise-exec: payload executable is not absolute", file=sys.stderr)
        return 2
    try:
        os.execv(payload[0], payload)
    except OSError as exc:
        print(f"holder-supervise-exec: exec failed: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
