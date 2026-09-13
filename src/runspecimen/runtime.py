"""Deterministic provenance for the executable selected by a contract.

This module captures comprehensive runtime provenance including:
- The resolved executable path and its SHA-256 hash
- The interpreter (if the command is a script)
- Environment variables from a contract-specified allowlist (names/hashes only)
- Optional library dependency hashes (when capture_libs is enabled)

Provenance truthfulness principles:
- A configured interpreter MUST resolve to an executable and be fingerprinted
- The interpreter recorded MUST be the exact interpreter that will be launched
- Missing, non-executable, or mismatched interpreters cause hard failures
- Library capture explicitly reports unsupported platforms
- ldd is only invoked on the actual interpreter (not untrusted scripts)
"""

from __future__ import annotations

import os
import platform
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

# Platform support for library capture
_PLATFORM_SYSTEM = platform.system()


def _detect_interpreter(executable: Path) -> tuple[Path | None, list[str] | None]:
    """Detect if executable is a script and return its interpreter path and args.

    Reads the shebang line to determine the interpreter.
    Returns (interpreter_path, interpreter_args) or (None, None) if not a script.

    Safely handles:
    - Direct path shebangs: #!/usr/bin/python3 -u
    - Env-style shebangs: #!/usr/bin/env python3
    - Env with args: #!/usr/bin/env -S python3 -u (records only the interpreter)
    """
    try:
        with executable.open("rb") as f:
            first_line = f.readline(256)
        if not first_line.startswith(b"#!"):
            return None, None
        shebang = first_line[2:].decode("utf-8", errors="replace").strip()

        # Handle env-style shebangs: #!/usr/bin/env python3
        # Also handle: #!/usr/bin/env -S python3 -u (env with -S split args)
        if "/env" in shebang:
            parts = shebang.split()
            # Find the actual interpreter name (skip env and its flags)
            interp_idx = 1  # Default: first arg after env
            for i, part in enumerate(parts[1:], 1):
                if not part.startswith("-"):
                    interp_idx = i
                    break
            if interp_idx < len(parts):
                interp_name = parts[interp_idx]
                interp_args = parts[interp_idx + 1:] if interp_idx + 1 < len(parts) else []
                found = shutil.which(interp_name)
                if found:
                    return Path(found).resolve(), interp_args
        else:
            # Direct path shebang: #!/usr/bin/python3 -u
            parts = shebang.split()
            if parts:
                interp_path = Path(parts[0])
                interp_args = parts[1:] if len(parts) > 1 else []
                if interp_path.is_file() and os.access(str(interp_path), os.X_OK):
                    return interp_path.resolve(), interp_args
        return None, None
    except (OSError, ValueError):
        return None, None


def _capture_env_allowlist(allowlist: tuple[str, ...]) -> dict[str, str | None]:
    """Capture environment variables from the allowlist.

    Returns a dict mapping variable names to values (or None if not set).
    """
    result: dict[str, str | None] = {}
    for var in sorted(allowlist):
        result[var] = os.environ.get(var)
    return result


def _hash_env_allowlist(env_capture: dict[str, str | None]) -> str:
    """Compute a domain-separated hash of the captured environment variables.

    Uses a versioned domain tag to prevent cross-context hash collisions.
    """
    # Domain-separated hash with versioned prefix
    domain_tag = b"runspecimen.env_allowlist.v1\x00"
    env_bytes = canonical_json_bytes(env_capture)
    return sha256_bytes(domain_tag + env_bytes)


def _get_linked_libraries(
    executable: Path,
    *,
    is_trusted: bool = False,
) -> tuple[list[str], str | None]:
    """Get list of linked libraries for an executable.

    Args:
        executable: Path to the executable to inspect
        is_trusted: If True, the executable has been validated as a known
                   interpreter and is safe to inspect with ldd. If False,
                   refuse to run ldd on potentially malicious binaries.

    Returns:
        (list of library paths, error_message or None)

        error_message is set when library capture cannot be performed:
        - Platform not supported (non-Linux)
        - ldd not available
        - Executable is untrusted (is_trusted=False)

    Security note: ldd on some platforms may execute code in the binary being
    inspected. Only call with is_trusted=True for known-safe executables.
    """
    # Platform check
    if _PLATFORM_SYSTEM not in ("Linux",):
        return [], f"capture_libs not supported on {_PLATFORM_SYSTEM} (Linux only)"

    # Security: refuse to run ldd on untrusted binaries
    if not is_trusted:
        return [], "capture_libs skipped: binary not verified as trusted interpreter"

    # Check ldd availability
    if not shutil.which("ldd"):
        return [], "ldd not found on PATH"

    try:
        result = subprocess.run(
            ["ldd", str(executable)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return [], f"ldd returned exit code {result.returncode}"

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
        return sorted(libs), None
    except subprocess.TimeoutExpired:
        return [], "ldd timed out"
    except FileNotFoundError:
        return [], "ldd not found"
    except OSError as e:
        return [], f"ldd failed: {e}"


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
        interpreter_args: list[str] | None = None
        is_known_interpreter = False

        if runtime_spec.interpreter:
            # Use explicitly specified interpreter - MUST resolve and be executable
            interp_path = Path(runtime_spec.interpreter)
            if not interp_path.is_absolute():
                found = shutil.which(runtime_spec.interpreter)
                if found:
                    interpreter = Path(found).resolve()
                else:
                    raise ProvenanceError(
                        f"configured interpreter not found on PATH: {runtime_spec.interpreter!r}"
                    )
            else:
                if not interp_path.exists():
                    raise ProvenanceError(
                        f"configured interpreter does not exist: {runtime_spec.interpreter}"
                    )
                if not interp_path.is_file():
                    raise ProvenanceError(
                        f"configured interpreter is not a file: {runtime_spec.interpreter}"
                    )
                if not os.access(str(interp_path), os.X_OK):
                    raise ProvenanceError(
                        f"configured interpreter is not executable: {runtime_spec.interpreter}"
                    )
                interpreter = interp_path.resolve()

            # Configured interpreters are trusted (user explicitly specified them)
            is_known_interpreter = True
        else:
            # Auto-detect interpreter from shebang
            interpreter, interpreter_args = _detect_interpreter(executable)
            # Auto-detected interpreters from system paths are trusted
            if interpreter:
                is_known_interpreter = str(interpreter).startswith(("/usr/", "/bin/", "/opt/"))

        if interpreter:
            body["interpreter"] = str(interpreter)
            body["interpreter_sha256"] = sha256_file(interpreter)
            if interpreter_args:
                body["interpreter_args"] = interpreter_args

        # Capture environment variables from allowlist (names and presence only)
        if runtime_spec.env_allowlist:
            env_capture = _capture_env_allowlist(runtime_spec.env_allowlist)
            body["env_allowlist"] = list(runtime_spec.env_allowlist)
            # Only store hashes, not raw values (security: no secrets in artifacts)
            body["env_hash"] = _hash_env_allowlist(env_capture)

        # Optionally capture library hashes
        if runtime_spec.capture_libs:
            # For scripts, capture libraries of the interpreter, not the script
            lib_target = interpreter if interpreter else executable
            is_trusted = is_known_interpreter if interpreter else False

            libs, lib_error = _get_linked_libraries(lib_target, is_trusted=is_trusted)

            if lib_error:
                # Record the error rather than silently failing
                body["capture_libs_error"] = lib_error

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
