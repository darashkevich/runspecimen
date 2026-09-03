"""Crash-safe run state document."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.paths import STATE_FILENAME, ensure_dir


def state_path(state_dir: Path) -> Path:
    return state_dir / STATE_FILENAME


def load_state(state_dir: Path) -> dict[str, Any]:
    path = state_path(state_dir)
    if not path.exists():
        return {
            "phase": "none",
            "campaign_id": None,
            "run_id": None,
        }
    return read_json(path)


def save_state(state_dir: Path, state: dict[str, Any]) -> None:
    ensure_dir(state_dir)
    atomic_write_json(state_path(state_dir), state)


def update_state(state_dir: Path, **fields: Any) -> dict[str, Any]:
    state = load_state(state_dir)
    state.update(fields)
    save_state(state_dir, state)
    return state
