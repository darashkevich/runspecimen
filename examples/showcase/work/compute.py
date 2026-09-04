#!/usr/bin/env python3
"""Tiny showcase compute step."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "result.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"status": "ok", "answer": 42}, indent=2) + "\n", encoding="utf-8")
print("wrote", OUT)
