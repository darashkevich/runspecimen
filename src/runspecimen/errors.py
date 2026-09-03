"""Typed failures used across the CLI and library surface."""

from __future__ import annotations


class RunSpecimenError(Exception):
    """Base error; message is safe to print to users."""


class ContractError(RunSpecimenError):
    """Contract JSON failed schema or semantic validation."""


class ProvenanceError(RunSpecimenError):
    """Source or contract hashes do not match approval/state."""


class ApprovalError(RunSpecimenError):
    """Approval missing, stale, or not interactive."""


class PreflightError(RunSpecimenError):
    """Preflight refused to allow a run."""


class LeaseError(RunSpecimenError):
    """Could not acquire or hold the exclusive lease."""


class RunError(RunSpecimenError):
    """Execution failed at the orchestration layer."""


class PostflightError(RunSpecimenError):
    """Postflight assertions failed."""


class CertificateError(RunSpecimenError):
    """Certificate missing or verification failed."""


class PathEscapeError(RunSpecimenError):
    """A configured path escapes the workspace root."""
