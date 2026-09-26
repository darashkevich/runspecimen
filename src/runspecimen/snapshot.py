"""Workspace snapshot / recovery provider (local tar integration).

Evaluates existing tooling (stdlib tarfile) rather than inventing a new engine.
Restore defaults to a separate directory. In-place consequential restore requires
the ordinary authorization path (not implemented as silent overwrite here).
Does not promise rollback of DBs, published artifacts, or external side effects.
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Any, Protocol

from runspecimen.artifact import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    assert_artifact_version,
    assert_schema_kind,
    bind_artifact_digest,
    verify_artifact_digest,
)
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.errors import RunSpecimenError
from runspecimen.events import utc_now_iso
from runspecimen.hashutil import hash_source, sha256_file, iter_source_files
from runspecimen.paths import ensure_dir, ensure_within, resolve_workspace, validate_id, workspace_state_root


class SnapshotError(RunSpecimenError):
    """Snapshot create/restore failed."""


class SnapshotProvider(Protocol):
    name: str

    def create(self, *, workspace: Path, snapshot_id: str, roots: list[str], excludes: list[str]) -> dict[str, Any]:
        ...

    def preview_restore(
        self, *, workspace: Path, record: dict[str, Any], dest: Path
    ) -> dict[str, Any]:
        ...

    def restore(
        self, *, workspace: Path, record: dict[str, Any], dest: Path
    ) -> dict[str, Any]:
        ...


def snapshots_dir(workspace: Path) -> Path:
    return workspace_state_root(workspace) / "snapshots"


def snapshot_record_path(workspace: Path, snapshot_id: str) -> Path:
    return snapshots_dir(workspace) / validate_id(snapshot_id) / "snapshot_record.json"


def snapshot_archive_path(workspace: Path, snapshot_id: str) -> Path:
    return snapshots_dir(workspace) / validate_id(snapshot_id) / "tree.tar.gz"


class LocalTarSnapshotProvider:
    """Local gzip tar of declared source roots (tracked layout via hash_source rules)."""

    name = "local_tar"

    def create(
        self,
        *,
        workspace: Path,
        snapshot_id: str,
        roots: list[str],
        excludes: list[str],
    ) -> dict[str, Any]:
        workspace = resolve_workspace(workspace)
        sid = validate_id(snapshot_id)
        out_dir = snapshots_dir(workspace) / sid
        ensure_dir(out_dir)
        archive = snapshot_archive_path(workspace, sid)
        files = iter_source_files(workspace, roots, excludes)
        omissions: list[str] = [
            ".runspecimen (control plane excluded by hash defaults)",
            ".git and VCS metadata excluded by hash defaults",
            "symlinks refused (not archived)",
            "databases / published artifacts / external side effects are out of coverage",
        ]
        with tarfile.open(archive, "w:gz") as tar:
            for path in files:
                rel = path.relative_to(workspace).as_posix()
                tar.add(path, arcname=rel)

        source_hash, entries = hash_source(workspace, roots, excludes)
        archive_digest = sha256_file(archive)
        record = {
            "schema_kind": "snapshot_record",
            "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
            "id": sid,
            "provider": self.name,
            "created_at": utc_now_iso(),
            "roots": list(roots),
            "excludes": list(excludes),
            "source_hash": source_hash,
            "file_count": len(entries),
            "archive_relpath": f".runspecimen/snapshots/{sid}/tree.tar.gz",
            "archive_sha256": archive_digest,
            "coverage": {
                "includes": "files under declared roots after exclude rules",
                "omissions": omissions,
            },
            "integrity": {"archive_sha256": archive_digest, "source_hash": source_hash},
            "limitations": [
                "Does not roll back databases, published artifacts, or external side effects.",
                "Provider absence/failure must stay visible to operators.",
            ],
        }
        record = bind_artifact_digest(record)
        atomic_write_json(snapshot_record_path(workspace, sid), record)
        return record

    def _load_and_verify_archive(self, workspace: Path, record: dict[str, Any]) -> Path:
        verify_artifact_digest(record)
        archive = snapshot_archive_path(workspace, record["id"])
        if not archive.is_file():
            raise SnapshotError(
                f"snapshot archive unavailable: {archive} (provider={self.name})"
            )
        live = sha256_file(archive)
        if live != record.get("archive_sha256"):
            raise SnapshotError(
                f"snapshot archive integrity failure: expected {record.get('archive_sha256')}, got {live}"
            )
        return archive

    def preview_restore(
        self, *, workspace: Path, record: dict[str, Any], dest: Path
    ) -> dict[str, Any]:
        workspace = resolve_workspace(workspace)
        archive = self._load_and_verify_archive(workspace, record)
        dest = dest.expanduser().resolve()
        dest_refusal = _restore_dest_refusal_reason(workspace, dest)
        # Compare archive members to current workspace (not dest) for "would change".
        members: list[str] = []
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile():
                    members.append(m.name)

        would_add: list[str] = []
        would_overwrite: list[str] = []
        user_changes_preserved_if_separate = dest != workspace
        for rel in members:
            current = workspace / rel
            if not current.exists():
                would_add.append(rel)
            else:
                would_overwrite.append(rel)

        return {
            "ok": dest_refusal is None,
            "provider": self.name,
            "snapshot_id": record["id"],
            "dest": str(dest),
            "restore_target_is_workspace": dest == workspace,
            "dest_refusal": dest_refusal,
            "member_count": len(members),
            "would_add": would_add[:200],
            "would_overwrite": would_overwrite[:200],
            "truncated": len(would_add) > 200 or len(would_overwrite) > 200,
            "user_changes": {
                "default_dest_is_separate_directory": True,
                "in_place_requires_explicit_authorization": True,
                "note": (
                    "Preview does not modify files. Restore to a separate directory by default "
                    "so current workspace changes are not silently discarded."
                    if user_changes_preserved_if_separate
                    else "In-place restore would overwrite workspace files; refused without explicit flag."
                ),
            },
            "coverage_omissions": (record.get("coverage") or {}).get("omissions", []),
        }

    def restore(
        self, *, workspace: Path, record: dict[str, Any], dest: Path
    ) -> dict[str, Any]:
        workspace = resolve_workspace(workspace)
        dest = dest.expanduser().resolve()
        refusal = _restore_dest_refusal_reason(workspace, dest)
        if refusal is not None:
            raise SnapshotError(refusal)
        archive = self._load_and_verify_archive(workspace, record)
        ensure_dir(dest)
        with tarfile.open(archive, "r:gz") as tar:
            _safe_extractall(tar, dest)
        return {
            "ok": True,
            "provider": self.name,
            "snapshot_id": record["id"],
            "dest": str(dest),
            "archive_sha256": record.get("archive_sha256"),
            "note": "Restored to a separate directory; compare before any authorized replace.",
        }


def _restore_dest_refusal_reason(workspace: Path, dest: Path) -> str | None:
    """Return a refusal reason when dest overlaps the live workspace hierarchy."""
    workspace = workspace.resolve()
    dest = dest.expanduser().resolve()
    if dest == workspace:
        return (
            "refusing in-place restore to the live workspace; "
            "choose --dest outside the workspace hierarchy (consequential in-place "
            "restore must use the ordinary authorization lifecycle, not this helper)"
        )
    try:
        dest.relative_to(workspace)
    except ValueError:
        pass
    else:
        return (
            "refusing restore into the live workspace tree; "
            "choose --dest outside the workspace hierarchy"
        )
    try:
        workspace.relative_to(dest)
    except ValueError:
        pass
    else:
        return (
            "refusing restore to an ancestor of the live workspace; "
            "archive members (e.g. work/) would materialize beside or over the live "
            "tree. Choose an explicit --dest outside the workspace hierarchy."
        )
    return None


def _assert_safe_restore_dest(workspace: Path, dest: Path) -> None:
    reason = _restore_dest_refusal_reason(workspace, dest)
    if reason is not None:
        raise SnapshotError(reason)


def _safe_extractall(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract archive members so paths cannot escape the explicit dest root."""
    dest = dest.resolve()
    for member in tar.getmembers():
        name = member.name
        if not name or name.startswith("/") or name.startswith("\\"):
            raise SnapshotError(f"refusing absolute archive member path: {name!r}")
        # Normalize and reject traversal / escape.
        target = (dest / name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise SnapshotError(
                f"archive member escapes restore dest: {name!r} -> {target}"
            ) from exc
        if member.issym() or member.islnk():
            raise SnapshotError(f"refusing symlink/hardlink archive member: {name!r}")
    try:
        tar.extractall(dest, filter=tarfile.data_filter)  # type: ignore[arg-type]
    except TypeError:
        tar.extractall(dest)
    except AttributeError:
        tar.extractall(dest)


_PROVIDERS: dict[str, SnapshotProvider] = {
    LocalTarSnapshotProvider.name: LocalTarSnapshotProvider(),
}


def get_snapshot_provider(name: str = "local_tar") -> SnapshotProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise SnapshotError(f"snapshot provider unavailable: {name!r}")
    return provider


def load_snapshot_record(workspace: Path, snapshot_id: str) -> dict[str, Any]:
    path = snapshot_record_path(workspace, snapshot_id)
    if not path.is_file():
        raise SnapshotError(f"snapshot record not found: {snapshot_id}")
    doc = read_json(path)
    assert_schema_kind(doc.get("schema_kind"), expected="snapshot_record")
    assert_artifact_version(doc.get("schema_version"))
    verify_artifact_digest(doc)
    return doc


def compare_snapshot_to_workspace(workspace: Path, record: dict[str, Any]) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    verify_artifact_digest(record)
    live_hash, _ = hash_source(
        workspace, list(record.get("roots") or []), list(record.get("excludes") or [])
    )
    match = live_hash == record.get("source_hash")
    return {
        "snapshot_id": record["id"],
        "recorded_source_hash": record.get("source_hash"),
        "current_source_hash": live_hash,
        "matches": match,
        "note": (
            "Match means declared roots hash equal the snapshot; "
            "it does not prove absence of temporary mid-lifetime modifications."
        ),
    }
