#!/usr/bin/env python3
"""Thin re-export of the canonical RunSpecimen MCP server.

Behavior matches ``plugins/runspecimen/scripts/runspecimen_mcp.py``.
This entry point adds no tools. Approve and settle stay excluded.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CANONICAL = Path(__file__).resolve().parents[2] / "scripts" / "runspecimen_mcp.py"


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "runspecimen"
SERVER_VERSION = "0.2.0-rc.15"

ALLOWED = frozenset({
    "about",
    "dashboard",
    "doctor",
    "validate",
    "status",
    "preflight",
    "run",
    "postflight",
    "verify",
})

TOOLS: list[dict[str, Any]] = [
    {
        "name": "about",
        "description": "Print RunSpecimen product summary (no workspace required).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "doctor",
        "description": "Check local RunSpecimen installation and workspace readiness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string", "description": "Workspace path"},
            },
            "required": ["workspace"],
            "additionalProperties": False,
        },
    },
    {
        "name": "validate",
        "description": "Validate a RunSpecimen contract against the workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string"},
                "contract": {"type": "string"},
            },
            "required": ["workspace", "contract"],
            "additionalProperties": False,
        },
    },
    {
        "name": "status",
        "description": "Read-only campaign/run status diagnosis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string"},
                "campaign_id": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["workspace", "campaign_id", "run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "preflight",
        "description": "Run preflight after the human has approved on a real TTY.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string"},
                "contract": {"type": "string"},
            },
            "required": ["workspace", "contract"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run",
        "description": "Execute one bounded run after preflight (never approves).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string"},
                "contract": {"type": "string"},
            },
            "required": ["workspace", "contract"],
            "additionalProperties": False,
        },
    },
    {
        "name": "postflight",
        "description": "Assert outcomes and issue a receipt after run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string"},
                "contract": {"type": "string"},
            },
            "required": ["workspace", "contract"],
            "additionalProperties": False,
        },
    },
    {
        "name": "verify",
        "description": "Verify receipts with campaign-id and run-id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string"},
                "contract": {"type": "string"},
                "campaign_id": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["workspace", "contract", "campaign_id", "run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "dashboard",
        "description": (
            "Start the loopback read-only dashboard (blocking). Prefer a "
            "detached terminal; cannot approve."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {"type": "string"},
                "contract": {"type": "string"},
                "open": {"type": "boolean", "default": False},
            },
            "required": ["workspace", "contract"],
            "additionalProperties": False,
        },
    },
]


_impl = _load()

PROTOCOL_VERSION = _impl.PROTOCOL_VERSION
SERVER_NAME = _impl.SERVER_NAME
SERVER_VERSION = _impl.SERVER_VERSION
ALLOWED = _impl.ALLOWED
TOOLS = _impl.TOOLS
main = _impl.main


if __name__ == "__main__":
    raise SystemExit(main())
