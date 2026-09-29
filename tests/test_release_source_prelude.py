"""Release freeze must not start until the reviewed commit is isolated.

These tests drive release_source_prelude.sh. They do not freeze PyInstaller
or call xcodebuild. A dirty or unexpected checkout must exit before the
freeze command. A commit created by that command must fail the release.
"""

from __future__ import annotations

import os
import pathlib
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

    def test_development_freeze_still_runs_on_a_dirty_tree(self) -> None:
        _init_repo(self.repo)
        (self.repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
        completed = self._run(gate=False, expected=None, freeze='touch "$RS_MARKER"')
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(self.freeze_marker.exists())
