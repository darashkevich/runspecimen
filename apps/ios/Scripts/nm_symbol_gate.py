"""Fatal nm symbol gate for shipping Observe Release objects.

Negative fixtures do not build or install an iOS app. A real simulator or
device Release scan is a separate human/CI step. This is not App Store
acceptance and not a Face ID proof.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

FORBIDDEN = (
    "beforeConsumptionDecision",
    "beforeExclusiveAccess",
    "beforeFinalSignatureDecision",
    "retireUnusableKey",
)

# One checked nm result per inode generation. A later failure is not hidden.
_NM_CACHE: dict[tuple[str, int, int], str] = {}


class SymbolGateError(Exception):
    """The scan target failed closed."""


def nm_defined_symbols(path: Path) -> str:
    """Return cached nm -Uj text. A non-zero nm status is fatal."""
    if not path.is_file():
        raise SymbolGateError(f"missing scan target: {path}")
    try:
        st = path.stat()
    except OSError as exc:
        raise SymbolGateError(f"unreadable scan target: {path}") from exc
    key = (str(path.resolve()), st.st_mtime_ns, st.st_size)
    cached = _NM_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        proc = subprocess.run(
            ["nm", "-Uj", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SymbolGateError(f"nm could not run: {path}") from exc
    if proc.returncode != 0:
        raise SymbolGateError(f"nm failed on {path}: {proc.stderr.strip()}")
    _NM_CACHE[key] = proc.stdout
    return proc.stdout


def assert_forbidden_absent(nm_text: str, *, label: str) -> None:
    for name in FORBIDDEN:
        if name in nm_text:
            raise SymbolGateError(f"{label} contains forbidden symbol {name}")


def scan_path(path: Path) -> str:
    text = nm_defined_symbols(path)
    assert_forbidden_absent(text, label=str(path))
    return text
