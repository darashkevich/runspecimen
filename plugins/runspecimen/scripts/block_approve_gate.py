#!/usr/bin/env python3
"""PreToolUse gate: refuse agent-driven RunSpecimen approval / settle paths.

Claude Code and Grok Build invoke this hook with JSON on stdin. When the tool
input looks like typing APPROVE, running ``runspecimen approve``, settling
remote-confirm, or calling a forbidden companion approve path, deny the call.
Silence (exit 0, no JSON) means the hook takes no permission decision.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any


DENY_REASON = (
    "RunSpecimen approval is human-only on a real TTY. Do not type APPROVE, "
    "run `runspecimen approve`, settle remote-confirm, or call companion "
    "/v1/approve. Ask the user to approve in their terminal, then continue "
    "with validate → preflight → run → postflight → verify."
)

# Patterns that indicate an agent is trying to approve or settle for the human.
_PATTERNS = (
    re.compile(r"\brunspecimen(?:\.py)?\s+approve\b", re.I),
    re.compile(r"\brunspecimen_adapter\.py\s+approve\b", re.I),
    re.compile(r"\becho\s+['\"]?APPROVE['\"]?", re.I),
    re.compile(r"\bprintf\s+['\"]?APPROVE['\"]?", re.I),
    re.compile(r"\bAPPROVE\b"),
    re.compile(r"/v1/approve\b", re.I),
    re.compile(r"\bremote[_-]?confirm\b.*\bsettle\b", re.I),
    re.compile(r"\bsettle\b.*\bremote[_-]?confirm\b", re.I),
    re.compile(r"\brunspecimen(?:\.py)?\s+remote-confirm\b", re.I),
)


def _collect_text(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_text(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_text(item, out)


def should_deny(payload: dict[str, Any]) -> bool:
    blobs: list[str] = []
    tool_name = str(payload.get("tool_name") or payload.get("toolName") or "")
    if tool_name:
        blobs.append(tool_name)
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    _collect_text(tool_input, blobs)
    # Some hosts nest the command under input / arguments.
    _collect_text(payload.get("input"), blobs)
    _collect_text(payload.get("arguments"), blobs)
    text = "\n".join(blobs)
    if not text.strip():
        return False
    return any(pattern.search(text) for pattern in _PATTERNS)


def deny_payload() -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": DENY_REASON,
        }
    }


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    if should_deny(payload):
        json.dump(deny_payload(), sys.stdout)
        sys.stdout.write("\n")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
