"""Isolated evidence directories for holder and macOS smoke scripts.

These tests do not install a holder, do not contact a live daemon, and do not
invoke biometrics. A PATH stub stands in for ``swift``.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "apps/holder/Scripts/isolated_evidence.sh"
HOLDER = REPO / "apps/holder/Scripts/test_holder_isolated.sh"
SMOKE = REPO / "apps/macos/Scripts/smoke_macos.sh"
CODESIGN = "resource fork, Finder information, or similar detritus not allowed"


def _bash(script: str, *, env: dict[str, str] | None = None, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("RS_HOLDER_SOCKET", None)
    merged.pop("RS_HOLDER_INSTALL_CONSENT", None)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        env=merged,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _swift_stub(directory: Path) -> None:
    stub = directory / "swift"
    stub.write_text(
        "#!/bin/bash\n"
        "if [[ \"${1:-}\" == package ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == test ]]; then\n"
        "  echo \"MARKER:${RS_EVIDENCE_MARKER:-unset}\"\n"
        "  printf 'SCRATCH:'\n"
        "  printf ' %s' \"$@\"\n"
        "  printf '\\n'\n"
        "  if [[ \"${RS_EVIDENCE_ZERO:-}\" == 1 ]]; then\n"
        "    echo 'Executed 0 tests, with 0 failures'\n"
        "    exit 0\n"
        "  fi\n"
        "  if [[ -n \"${RS_EVIDENCE_SWIFT_BODY:-}\" ]]; then\n"
        "    printf '%s\\n' \"$RS_EVIDENCE_SWIFT_BODY\"\n"
        "    exit \"${RS_EVIDENCE_SWIFT_RC:-1}\"\n"
        "  fi\n"
        "  echo 'Executed 3 tests, with 0 failures'\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected swift: $*\" >&2\n"
        "exit 99\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


class IsolatedScriptEvidenceTests(unittest.TestCase):
    def test_concurrent_holder_logs_stay_separate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-evidence-") as raw:
            root = Path(raw)
            stub_bin = root / "bin"
            stub_bin.mkdir()
            _swift_stub(stub_bin)
            work = root / "work"
            work.mkdir()
            canary = work / "rs-holder-swift-first.log"
            canary.write_text("CANARY\n", encoding="utf-8")
            predictable = work / "rs-holder-swift.PREDICT"
            predictable.mkdir()
            (predictable / "keep").write_text("keep\n", encoding="utf-8")
            base = os.environ.copy()
            base.pop("RS_HOLDER_SOCKET", None)
            base.pop("RS_HOLDER_INSTALL_CONSENT", None)
            env = {
                **base,
                "TMPDIR": str(work),
                "PATH": f"{stub_bin}:/usr/bin:/bin",
                "RS_EVIDENCE_MARKER": "alpha",
            }
            other = dict(env)
            other["RS_EVIDENCE_MARKER"] = "beta"
            first = subprocess.Popen(
                ["bash", str(HOLDER)],
                cwd=REPO,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            second = subprocess.Popen(
                ["bash", str(HOLDER)],
                cwd=REPO,
                env=other,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            out_a, err_a = first.communicate(timeout=30)
            out_b, err_b = second.communicate(timeout=30)
            self.assertEqual(first.returncode, 0, out_a + err_a)
            self.assertEqual(second.returncode, 0, out_b + err_b)
            self.assertIn("MARKER:alpha", out_a)
            self.assertNotIn("MARKER:beta", out_a)
            self.assertIn("MARKER:beta", out_b)
            self.assertNotIn("MARKER:alpha", out_b)
            self.assertIn("HOLDER_FIRST_PASS: OK", out_a)
            self.assertIn("HOLDER_FIRST_PASS: OK", out_b)
            scratch_a = next(line for line in out_a.splitlines() if line.startswith("SCRATCH:"))
            scratch_b = next(line for line in out_b.splitlines() if line.startswith("SCRATCH:"))
            self.assertNotEqual(scratch_a, scratch_b)
            self.assertIn("/scratch", scratch_a)
            self.assertIn("/scratch", scratch_b)
            self.assertNotIn("HOLDER_EVIDENCE:", err_a)
            self.assertNotIn("HOLDER_EVIDENCE:", err_b)
            self.assertEqual(canary.read_text(encoding="utf-8"), "CANARY\n")
            self.assertEqual((predictable / "keep").read_text(encoding="utf-8"), "keep\n")
            self.assertEqual(list(work.glob("rs-holder-swift.*")), [predictable])
            self.assertFalse(list(work.glob("rs-holder-swift-kept.*")))
            self.assertNotIn("rs-holder-swift.$$", HOLDER.read_text(encoding="utf-8"))
            self.assertNotIn("rs-holder-swift-first.log", HOLDER.read_text(encoding="utf-8"))

    def test_zero_test_run_is_refused_and_log_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-evidence-") as raw:
            root = Path(raw)
            stub_bin = root / "bin"
            stub_bin.mkdir()
            _swift_stub(stub_bin)
            work = root / "work"
            work.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "TMPDIR": str(work),
                    "PATH": f"{stub_bin}:/usr/bin:/bin",
                    "RS_EVIDENCE_ZERO": "1",
                    "RS_EVIDENCE_MARKER": "zero",
                }
            )
            env.pop("RS_HOLDER_SOCKET", None)
            env.pop("RS_HOLDER_INSTALL_CONSENT", None)
            proc = subprocess.run(
                ["bash", str(HOLDER)],
                cwd=REPO,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            combined = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, combined)
            self.assertIn("HOLDER_FIRST_PASS: FAIL — zero tests ran", combined)
            self.assertIn("HOLDER_EVIDENCE:", proc.stderr)
            kept = [
                line.split("HOLDER_EVIDENCE:", 1)[1].strip()
                for line in proc.stderr.splitlines()
                if line.startswith("HOLDER_EVIDENCE:")
            ]
            self.assertEqual(len(kept), 1)
            kept_dir = Path(kept[0])
            self.assertTrue((kept_dir / "first.log").is_file())
            self.assertIn("Executed 0 tests", (kept_dir / "first.log").read_text(encoding="utf-8"))
            self.assertFalse((kept_dir / "scratch").exists())
            self.assertEqual(list(work.glob("rs-holder-swift.*")), [])
            self.assertEqual(list(work.glob("rs-holder-swift-kept.*")), [kept_dir])

    def test_environment_refusal_does_not_call_swift(self) -> None:
        for extra in (
            {"RS_HOLDER_SOCKET": "/private/tmp/must-not-connect.sock"},
            {"RS_HOLDER_INSTALL_CONSENT": "yes"},
        ):
            with self.subTest(extra=extra):
                with tempfile.TemporaryDirectory(prefix="rs-evidence-") as raw:
                    work = Path(raw)
                    env = os.environ.copy()
                    env["TMPDIR"] = str(work)
                    env["PATH"] = "/usr/bin:/bin"
                    env.pop("RS_HOLDER_SOCKET", None)
                    env.pop("RS_HOLDER_INSTALL_CONSENT", None)
                    env.update(extra)
                    proc = subprocess.run(
                        ["bash", str(HOLDER)],
                        cwd=REPO,
                        env=env,
                        text=True,
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    combined = proc.stdout + proc.stderr
                    self.assertEqual(proc.returncode, 2, combined)
                    self.assertIn("REFUSED", combined)
                    self.assertNotIn("HOLDER_FIRST_PASS: running", combined)
                    self.assertNotIn("swift test", combined)
                    self.assertEqual(list(work.iterdir()), [])

    def test_assertion_plus_codesign_does_not_retry(self) -> None:
        cases = {
            "codesign-only": (1, CODESIGN + "\n", "retry"),
            "assertion-only": (1, "Test Case Example failed\n", "assertion"),
            "both": (1, CODESIGN + "\nXCTAssertEqual failed\n", "assertion"),
            "issue-recorded": (1, "Issue recorded\n" + CODESIGN + "\n", "assertion"),
            "signed-at-path-and-failed": (
                1,
                "code object is not signed at path\nerror: -[HolderTests testOne] : failed\n",
                "assertion",
            ),
            "empty-failure": (1, "", "assertion"),
            "success-with-assertion-text": (0, "XCTAssertEqual failed\n" + CODESIGN + "\n", "ok"),
        }
        for name, (rc, body, expected) in cases.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory(prefix="rs-evidence-") as raw:
                    log = Path(raw) / "first.log"
                    log.write_text(body, encoding="utf-8")
                    proc = _bash(
                        f'source "{LIB}"; rs_smoke_first_pass_disposition {rc} "{log}"',
                        env={"TMPDIR": raw},
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(proc.stdout.strip(), expected)

    def test_cleanup_removes_only_the_created_directory(self) -> None:
        script = f'''
set -euo pipefail
source "{LIB}"
canary="$TMPDIR/shared-canary"
printf 'safe\\n' > "$canary"
created="$(rs_evidence_create rs-holder-swift)"
printf 'log\\n' > "$created/first.log"
mkdir "$created/scratch"
other="$(rs_evidence_create rs-holder-swift)"
printf 'other\\n' > "$other/first.log"
rs_evidence_cleanup "$created" rs-holder-swift
test ! -d "$created"
test -f "$other/first.log"
test -f "$canary"
if rs_evidence_cleanup "$TMPDIR" rs-holder-swift; then
  echo cleaned-root
  exit 1
fi
if rs_evidence_cleanup "$other/scratch" rs-holder-swift; then
  echo cleaned-scratch
  exit 1
fi
ln -s "$other" "$TMPDIR/rs-holder-swift.linked"
if rs_evidence_cleanup "$TMPDIR/rs-holder-swift.linked" rs-holder-swift; then
  echo cleaned-link
  exit 1
fi
test -d "$other"
test -f "$canary"
rs_evidence_cleanup "$other" rs-holder-swift
test ! -d "$other"
'''
        with tempfile.TemporaryDirectory(prefix="rs-evidence-") as raw:
            proc = _bash(script, env={"TMPDIR": raw})
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((Path(raw) / "shared-canary").is_file())

    def test_scripts_do_not_use_fixed_evidence_names(self) -> None:
        holder = HOLDER.read_text(encoding="utf-8")
        smoke = SMOKE.read_text(encoding="utf-8")
        self.assertIn("rs_evidence_create rs-holder-swift", holder)
        self.assertIn('FIRST_LOG="$EVIDENCE/first.log"', holder)
        self.assertIn("rs_log_has_executed_tests", holder)
        self.assertIn("rs_evidence_cleanup", holder)
        self.assertNotIn("mkdir -p", holder)
        self.assertIn("rs_evidence_create rs-macos-smoke", smoke)
        self.assertIn("rs_smoke_first_pass_disposition", smoke)
        self.assertIn('FIRST_LOG="$EVIDENCE/first.log"', smoke)
        for banned in (
            "rs-macos-swift-first.log",
            "rs-holder-swift-first.log",
            "/tmp/rs-stage-helper.out",
            "/tmp/rs-freeze.out",
            "/tmp/rs-build-help.out",
            "/tmp/rs-doctor.out",
            "/tmp/rs-frozen-build.out",
            "/tmp/rs-mas-build.out",
            "/tmp/rs-mas-helper-shell.out",
            "/tmp/rs-export-gate.out",
            "/tmp/rs-mas-fail.out",
        ):
            self.assertNotIn(banned, smoke)
            self.assertNotIn(banned, holder)


if __name__ == "__main__":
    unittest.main()
