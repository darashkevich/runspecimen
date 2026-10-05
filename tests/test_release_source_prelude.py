"""Release freeze must not start until the reviewed commit is isolated.

These tests drive release_source_prelude.sh. They do not freeze PyInstaller
or call xcodebuild. A dirty or unexpected checkout must exit before the
freeze command. A commit created by that command must fail the release.
Entrypoints that leave RS_REPO unset must resolve the repository root.
The production re-entry runs archive_mas.sh with RS_REPO removed.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRELUDE = ROOT / "apps" / "macos" / "Scripts" / "release_source_prelude.sh"


def _git(repo: pathlib.Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_repo(repo: pathlib.Path) -> str:
    repo.mkdir()
    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "tracked.txt")
    _git(
        repo,
        "-c",
        "user.email=qa@example.com",
        "-c",
        "user.name=QA",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "init",
    )
    return _git(repo, "rev-parse", "HEAD")


class ReleaseSourcePreludeTests(unittest.TestCase):
    def setUp(self) -> None:
        base = pathlib.Path("/tmp/rs-release-prelude")
        base.mkdir(exist_ok=True)
        self.root = base / self.id().replace(".", "_")
        subprocess.run(["rm", "-rf", str(self.root)], check=True)
        self.root.mkdir()
        self.repo = self.root / "src"
        self.freeze_marker = self.root / "freeze-ran"
        self.generate_marker = self.root / "generate-ran"
        self.seen_repo = self.root / "seen-repo"

    def tearDown(self) -> None:
        if self.repo.exists():
            subprocess.run(["git", "-C", str(self.repo), "worktree", "prune"], check=False)
        subprocess.run(["rm", "-rf", str(self.root)], check=False)

    def _run(self, *, gate: bool, expected: str | None, freeze: str, generate: str = "true") -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["RS_REPO"] = str(self.repo)
        env["RS_PRELUDE_ONLY"] = "1"
        env["RS_FREEZE_CMD"] = freeze
        env["RS_GENERATE_CMD"] = generate
        env["RS_MARKER"] = str(self.freeze_marker)
        env["RS_GENERATE_MARKER"] = str(self.generate_marker)
        env["RS_SEEN_REPO"] = str(self.seen_repo)
        env.pop("RS_RELEASE_ISOLATED", None)
        if gate:
            env["RS_RELEASE_GATE"] = "1"
            env["RS_EXPECTED_GIT_COMMIT"] = expected or ""
        else:
            env.pop("RS_RELEASE_GATE", None)
            env.pop("RS_EXPECTED_GIT_COMMIT", None)
        return subprocess.run(
            ["bash", str(PRELUDE)],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_dirty_source_is_refused_before_freeze(self) -> None:
        sha = _init_repo(self.repo)
        tracked = self.repo / "tracked.txt"
        tracked.write_text("dirty\n", encoding="utf-8")
        completed = self._run(
            gate=True,
            expected=sha,
            freeze='touch "$RS_MARKER"',
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("dirty source", completed.stderr)
        self.assertFalse(self.freeze_marker.exists())
        self.assertFalse(self.generate_marker.exists())
        self.assertEqual(_git(self.repo, "worktree", "list").count("\n"), 0)

    def test_wrong_expected_commit_is_refused_before_freeze(self) -> None:
        _init_repo(self.repo)
        completed = self._run(
            gate=True,
            expected="ab" * 20,
            freeze='touch "$RS_MARKER"',
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not match the expected candidate", completed.stderr)
        self.assertFalse(self.freeze_marker.exists())
        self.assertFalse(self.generate_marker.exists())

    def test_a_commit_during_freeze_is_refused_before_project_generation(self) -> None:
        sha = _init_repo(self.repo)
        freeze = (
            'touch "$RS_MARKER"\n'
            'printf "\\nchanged\\n" >> "$RS_REPO/tracked.txt"\n'
            'git -C "$RS_REPO" add tracked.txt\n'
            "git -C \"$RS_REPO\" -c user.email=qa@example.com -c user.name=QA "
            '-c commit.gpgsign=false commit -q -m "during freeze"\n'
        )
        completed = self._run(
            gate=True,
            expected=sha,
            freeze=freeze,
            generate='touch "$RS_GENERATE_MARKER"',
        )
        self.assertNotEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("changed during the build", completed.stderr)
        self.assertTrue(self.freeze_marker.exists())
        self.assertFalse(self.generate_marker.exists())
        self.assertEqual(_git(self.repo, "rev-parse", "HEAD"), sha)
        self.assertEqual(_git(self.repo, "worktree", "list").count("\n"), 0)

    def test_release_freeze_runs_in_an_isolated_candidate(self) -> None:
        sha = _init_repo(self.repo)
        completed = self._run(
            gate=True,
            expected=sha,
            freeze='printf %s "$RS_REPO" > "$RS_SEEN_REPO"',
            generate='touch "$RS_GENERATE_MARKER"',
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        seen = self.seen_repo.read_text(encoding="utf-8")
        self.assertNotEqual(pathlib.Path(seen).resolve(), self.repo.resolve())
        self.assertFalse(pathlib.Path(seen).exists())
        self.assertTrue(self.generate_marker.exists())
        self.assertEqual(_git(self.repo, "rev-parse", "HEAD"), sha)
        self.assertEqual(_git(self.repo, "status", "--porcelain"), "")

    def test_release_gate_refuses_build_app_before_compilation(self) -> None:
        script = ROOT / "apps" / "macos" / "Scripts" / "build_app.sh"
        env = os.environ.copy()
        env["RS_RELEASE_GATE"] = "1"
        completed = subprocess.run(
            ["bash", str(script), "--mas"],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("before any compilation", completed.stderr)
        self.assertNotIn("freezing self-contained helper", completed.stdout)

    def _run_real_entrypoint(
        self,
        argv: list[str],
        *,
        cwd: pathlib.Path,
        seen: pathlib.Path,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for key in (
            "RS_REPO",
            "RS_RELEASE_GATE",
            "RS_RELEASE_ISOLATED",
            "RS_EXPECTED_GIT_COMMIT",
            "RS_PRELUDE_ONLY",
            "RS_SOURCE_STATE_DIR",
        ):
            env.pop(key, None)
        env["RS_FREEZE_CMD"] = f'printf %s "$RS_REPO" > "{seen}"'
        env["RS_GENERATE_CMD"] = "true"
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, env=env)

    def test_direct_prelude_without_rs_repo_uses_repository_root(self) -> None:
        seen = self.root / "seen-repo"
        completed = self._run_real_entrypoint(
            ["bash", "apps/macos/Scripts/release_source_prelude.sh"],
            cwd=ROOT,
            seen=seen,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual(pathlib.Path(seen.read_text(encoding="utf-8")).resolve(), ROOT.resolve())
        self.assertNotEqual(pathlib.Path(seen.read_text(encoding="utf-8")).resolve(), (ROOT / "apps").resolve())

    def test_prelude_started_from_macos_directory_without_rs_repo(self) -> None:
        seen = self.root / "seen-from-macos"
        completed = self._run_real_entrypoint(
            ["bash", "Scripts/release_source_prelude.sh"],
            cwd=ROOT / "apps" / "macos",
            seen=seen,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual(pathlib.Path(seen.read_text(encoding="utf-8")).resolve(), ROOT.resolve())

    def test_production_archive_reentry_unsets_rs_repo(self) -> None:
        """The release path re-execs archive_mas.sh with RS_REPO removed.

        A stub archive stands in for xcodebuild. It follows the same
        isolated-versus-caller branch as archive_mas.sh and then runs the
        prelude. The fixture repo is committed so the detached worktree
        contains those scripts. This test does not set RS_REPO or
        RS_PRELUDE_ONLY.
        """
        repo = self.root / "fixture"
        scripts = repo / "apps" / "macos" / "Scripts"
        scripts.mkdir(parents=True)
        shutil.copy(PRELUDE, scripts / "release_source_prelude.sh")
        shutil.copy(ROOT / "apps" / "macos" / "Scripts" / "verify_mas_runtime.py", scripts / "verify_mas_runtime.py")
        archive = scripts / "archive_mas.sh"
        archive.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'cd "$(dirname "$0")/.."\n'
            'if [[ "${RS_RELEASE_GATE:-}" == "1" && "${RS_RELEASE_ISOLATED:-}" != "1" ]]; then\n'
            "  ./Scripts/release_source_prelude.sh\n"
            "  exit $?\n"
            "fi\n"
            "./Scripts/release_source_prelude.sh\n"
            'printf %s "$(cd "$(dirname "$0")/../../.." && pwd)" > "${RS_ARCHIVE_ROOT_SEEN:?}"\n',
            encoding="utf-8",
        )
        os.chmod(archive, 0o755)
        os.chmod(scripts / "release_source_prelude.sh", 0o755)
        (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
        _git(repo, "init", "-q")
        _git(repo, "add", "tracked.txt", "apps")
        _git(
            repo,
            "-c",
            "user.email=qa@example.com",
            "-c",
            "user.name=QA",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "fixture",
        )
        sha = _git(repo, "rev-parse", "HEAD")
        seen = self.root / "isolated-repo"
        archive_seen = self.root / "archive-root"
        env = os.environ.copy()
        for key in ("RS_REPO", "RS_RELEASE_ISOLATED", "RS_PRELUDE_ONLY", "RS_SOURCE_STATE_DIR"):
            env.pop(key, None)
        env["RS_RELEASE_GATE"] = "1"
        env["RS_EXPECTED_GIT_COMMIT"] = sha
        env["RS_SEEN_REPO"] = str(seen)
        env["RS_ARCHIVE_ROOT_SEEN"] = str(archive_seen)
        env["RS_FREEZE_CMD"] = 'test -d "$RS_REPO/apps/macos" && printf %s "$RS_REPO" > "$RS_SEEN_REPO"'
        env["RS_GENERATE_CMD"] = "true"
        completed = subprocess.run(
            ["bash", "apps/macos/Scripts/archive_mas.sh"],
            cwd=repo,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        isolated = pathlib.Path(seen.read_text(encoding="utf-8")).resolve()
        self.assertNotEqual(isolated, repo.resolve())
        self.assertTrue(str(isolated).endswith("/candidate") or isolated.name == "candidate")
        self.assertFalse(isolated.exists())
        self.assertNotIn("/apps/apps/", str(isolated))
        self.assertEqual(pathlib.Path(archive_seen.read_text(encoding="utf-8")).name, "candidate")
        self.assertEqual(_git(repo, "rev-parse", "HEAD"), sha)
        self.assertEqual(_git(repo, "status", "--porcelain"), "")

    def test_development_freeze_still_runs_on_a_dirty_tree(self) -> None:
        _init_repo(self.repo)
        (self.repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
        completed = self._run(gate=False, expected=None, freeze='touch "$RS_MARKER"')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(self.freeze_marker.exists())
