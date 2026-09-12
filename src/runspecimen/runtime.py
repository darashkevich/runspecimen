"""Deterministic provenance for the executable selected by a contract.

This module captures comprehensive runtime provenance including:
- The resolved executable path and its SHA-256 hash
- The interpreter (if the command is a script)
- Environment variables from a contract-specified allowlist
- Optional library dependency hashes (when capture_libs is enabled)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from runspecimen.contract import Contract
from runspecimen.errors import ProvenanceError
from runspecimen.hashutil import canonical_json_bytes, sha256_bytes, sha256_file
from runspecimen.paths import ensure_within

# Common interpreter patterns
KNOWN_INTERPRETERS = {
    "python", "python3", "python2",
    "ruby", "perl", "node", "nodejs",
    "bash", "sh", "zsh", "fish",
    "lua", "php", "Rscript",
}


def _detect_interpreter(executable: Path) -> Path | None:
    """Detect if executable is a script and return its interpreter path.
    
    Reads the shebang line to determine the interpreter.
    Returns None if not a script or interpreter not found.
    """
    try:
        with executable.open("rb") as f:
            first_line = f.readline(256)
        if not first_line.startswith(b"#!"):
            return None
        shebang = first_line[2:].decode("utf-8", errors="replace").strip()
        
        # Handle env-style shebangs: #!/usr/bin/env python3
        if shebang.startswith("/usr/bin/env "):
            parts = shebang.split()
            if len(parts) >= 2:
                interp_name = parts[1]
                found = shutil.which(interp_name)
                if found:
                    return Path(found).resolve()
        else:
            # Direct path shebang: #!/usr/bin/python3
            parts = shebang.split()
            if parts:
                interp_path = Path(parts[0])
                if interp_path.is_file() and os.access(str(interp_path), os.X_OK):
                    return interp_path.resolve()
        return None
    except (OSError, ValueError):
        return None


def _capture_env_allowlist(allowlist: tuple[str, ...]) -> dict[str, str | None]:
    """Capture environment variables from the allowlist.
    
    Returns a dict mapping variable names to values (or None if not set).
    """
    result: dict[str, str | None] = {}
    for var in sorted(allowlist):
        result[var] = os.environ.get(var)
    return result


def _hash_env_allowlist(env_capture: dict[str, str | None]) -> str:
    """Compute a hash of the captured environment variables."""
    # Sort and hash to get deterministic representation
    return sha256_bytes(canonical_json_bytes(env_capture))


def _get_linked_libraries(executable: Path) -> list[str]:
    """Get list of linked libraries for an executable (best effort).
    
    Uses ldd on Linux. Returns empty list on error or unsupported platforms.
    """
    try:
        result = subprocess.run(
            ["ldd", str(executable)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        
        libs: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            # ldd output: "libname.so => /path/to/lib (0x...)"
            if "=>" in line:
                parts = line.split("=>")
                if len(parts) >= 2:
                    lib_path = parts[1].strip().split()[0] if parts[1].strip() else ""
                    if lib_path and lib_path.startswith("/"):
                        libs.append(lib_path)
        return sorted(libs)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _hash_libraries(lib_paths: list[str]) -> dict[str, str]:
    """Hash each library file."""
    result: dict[str, str] = {}
    for lib_path in lib_paths:
        try:
            p = Path(lib_path)
            if p.is_file():
                result[lib_path] = sha256_file(p)
        except (OSError, ValueError):
            pass
    return result


def runtime_provenance(contract: Contract, workspace: Path) -> dict[str, Any]:
    """Resolve and hash argv[0] using the same cwd/PATH rules as execution.
    
    When contract.runtime is specified, also captures:
    - Interpreter provenance (if script)
    - Environment variables from allowlist
    - Library hashes (if capture_libs is enabled)
    """
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

    # Enhanced provenance when runtime spec is provided
    runtime_spec = contract.runtime
    if runtime_spec is not None:
        # Detect or use specified interpreter
        interpreter: Path | None = None
        if runtime_spec.interpreter:
            # Use explicitly specified interpreter
            interp_path = Path(runtime_spec.interpreter)
            if not interp_path.is_absolute():
                found = shutil.which(runtime_spec.interpreter)
                if found:
                    interpreter = Path(found).resolve()
            elif interp_path.is_file():
                interpreter = interp_path.resolve()
        else:
            # Auto-detect interpreter from shebang
            interpreter = _detect_interpreter(executable)
        
        if interpreter:
            body["interpreter"] = str(interpreter)
            body["interpreter_sha256"] = sha256_file(interpreter)
        
        # Capture environment variables from allowlist
        if runtime_spec.env_allowlist:
            env_capture = _capture_env_allowlist(runtime_spec.env_allowlist)
            body["env_allowlist"] = list(runtime_spec.env_allowlist)
            body["env_capture"] = env_capture
            body["env_hash"] = _hash_env_allowlist(env_capture)
        
        # Optionally capture library hashes
        if runtime_spec.capture_libs:
            libs = _get_linked_libraries(executable)
            if libs:
                lib_hashes = _hash_libraries(libs)
                body["linked_libraries"] = libs
                body["library_hashes"] = lib_hashes
                body["libraries_hash"] = sha256_bytes(canonical_json_bytes(lib_hashes))

    body["runtime_id"] = sha256_bytes(canonical_json_bytes(body))
    return body


def runtime_matches(approval: dict[str, Any], current: dict[str, Any]) -> tuple[bool, str]:
    """Check if current runtime provenance matches approval."""
    approved = approval.get("runtime")
    if not isinstance(approved, dict):
        return False, "approval missing runtime provenance"
    if approved.get("runtime_id") != current.get("runtime_id"):
        # Provide more detailed mismatch info
        mismatches: list[str] = []
        
        if approved.get("executable_sha256") != current.get("executable_sha256"):
            mismatches.append("executable changed")
        if approved.get("interpreter_sha256") != current.get("interpreter_sha256"):
            mismatches.append("interpreter changed")
        if approved.get("env_hash") != current.get("env_hash"):
            mismatches.append("environment variables changed")
        if approved.get("libraries_hash") != current.get("libraries_hash"):
            mismatches.append("linked libraries changed")
        
        if mismatches:
            return False, f"runtime provenance mismatch: {', '.join(mismatches)}"
        return False, "approval runtime provenance mismatch (runtime_id changed)"
    return True, "ok"
