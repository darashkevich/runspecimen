"""Mac-side attention / arm notifications for the companion (ADR-003 / ADR-004).

Default: local macOS banner + sound when attention is requested or a remote
confirm is armed. Focus / Do Not Disturb may still suppress banners — we do
not claim Focus bypass. Silent-only is not the product default for armed
remote-confirm on the Mac helper path.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any


def _escape_applescript_string(value: str) -> str:
    # JSON string encoding is a safe AppleScript string literal source.
    return json.dumps(value, ensure_ascii=False)


def notify_mac(
    *,
    title: str,
    message: str,
    sound: bool = True,
    sound_name: str = "Glass",
) -> dict[str, Any]:
    """Best-effort local macOS notification. No-op off Darwin or without osascript."""
    result: dict[str, Any] = {
        "ok": False,
        "platform": sys.platform,
        "delivered": False,
        "sound": bool(sound),
        "focus_note": (
            "macOS Focus / Do Not Disturb may suppress banners and sounds; "
            "RunSpecimen does not claim Focus bypass."
        ),
    }
    if sys.platform != "darwin":
        result["skipped"] = "not-darwin"
        return result
    if not shutil.which("osascript"):
        result["skipped"] = "osascript-missing"
        return result

    sound_clause = f" sound name {_escape_applescript_string(sound_name)}" if sound else ""
    script = (
        f"display notification {_escape_applescript_string(message)} "
        f"with title {_escape_applescript_string(title)}{sound_clause}"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
        return result

    result["ok"] = proc.returncode == 0
    result["delivered"] = proc.returncode == 0
    if proc.returncode != 0:
        result["error"] = (proc.stderr or proc.stdout or "osascript failed").strip()
    return result


def notify_attention_requested(*, message: str) -> dict[str, Any]:
    return notify_mac(
        title="RunSpecimen attention",
        message=message or "Companion requested attention on this Mac.",
        sound=True,
    )


def notify_remote_confirm_armed(*, campaign_id: str, run_id: str, ttl_sec: int) -> dict[str, Any]:
    return notify_mac(
        title="RunSpecimen remote confirm armed",
        message=(
            f"{campaign_id}/{run_id}: type the Mac challenge + APPROVE on the paired phone "
            f"(expires in {ttl_sec}s). Not TTY-equivalent."
        ),
        sound=True,
    )
