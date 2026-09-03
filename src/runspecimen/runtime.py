"""Deterministic provenance for the executable selected by a contract."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from runspecimen.contract import Contract
from runspecimen.errors import ProvenanceError
from runspecimen.hashutil import canonical_json_bytes, sha256_bytes, sha256_file
from runspecimen.paths import ensure_within


def runtime_provenance(contract: Contract, workspace: Path) -> dict[str, Any]:
    """Resolve and hash argv[0] using the same cwd/PATH rules as execution."""
    cwd = ensure_within(workspace, Path(contract.cwd), label="cwd")
    command = contract.argv[0]
    if os.sep in command:
        candidate = Path(command)
        executable = (cwd / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    else:
        # subprocess changes to ``cwd`` before resolving a PATH command.  Make
        # relative PATH entries resolve from that same directory so provenance
        # cannot describe a different executable than the one launched.
        search_entries: list[str] = []
        for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
            raw = Path(entry or ".")
            resolved = raw.resolve() if raw.is_absolute() else (cwd / raw).resolve()
            search_entries.append(str(resolved))
        found = shutil.which(command, path=os.pathsep.join(search_entries))
        if found is None:
            raise ProvenanceError(f"executable not found on PATH: {command!r}")
        executable = Path(found).resolve()

    if not executable.is_file():
        raise ProvenanceError(f"resolved executable is not a file: {executable}")
    if not os.access(str(executable), os.X_OK):
        raise ProvenanceError(f"resolved executable is not executable: {executable}")

    body: dict[str, Any] = {
        "argv0": command,
        "resolved_executable": str(executable),
        "executable_sha256": sha256_file(executable),
    }
    body["runtime_id"] = sha256_bytes(canonical_json_bytes(body))
    return body


def runtime_matches(approval: dict[str, Any], current: dict[str, Any]) -> tuple[bool, str]:
    approved = approval.get("runtime")
    if not isinstance(approved, dict):
        return False, "approval missing runtime provenance"
    if approved.get("runtime_id") != current.get("runtime_id"):
        return False, "approval runtime provenance mismatch (executable changed)"
    return True, "ok"
