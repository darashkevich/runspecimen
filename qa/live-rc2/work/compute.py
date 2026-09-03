#!/usr/bin/env python3
"""Small real-workflow smoke payload for RunSpecimen release QA."""

from __future__ import annotations

import json
from pathlib import Path


output = Path("outputs/result.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps({"status": "ok", "release": "0.2.0rc2"}, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"wrote {output}")
