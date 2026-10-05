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


def _load():
    spec = importlib.util.spec_from_file_location("runspecimen_mcp_canonical", _CANONICAL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"canonical MCP server missing: {_CANONICAL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_impl = _load()

PROTOCOL_VERSION = _impl.PROTOCOL_VERSION
SERVER_NAME = _impl.SERVER_NAME
SERVER_VERSION = _impl.SERVER_VERSION
ALLOWED = _impl.ALLOWED
TOOLS = _impl.TOOLS
main = _impl.main


if __name__ == "__main__":
    raise SystemExit(main())
