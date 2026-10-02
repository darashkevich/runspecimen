"""Ledger regressions for staging, trust order, and qualification.

E10 is isolated qualification. It is not a claim that a live exploit was reproduced.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runspecimen.execution_holder import ExecutionHolder
from runspecimen.holder_daemon import assert_support_before_secret
from runspecimen.holder_entry import validate_before_import
from runspecimen.holder_runtime import RuntimeTrustError
from runspecimen.native_bridge import platform_verifier_binary, supported_verifier_architecture


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "apps/holder/Scripts/build_install_holder.sh"
LIB = ROOT / "apps/holder/Scripts/holder_stage_lib.sh"


class HolderStageTests(unittest.TestCase):
    def test_dangerous_build_directories_are_not_deleted(self) -> None:
        script = f"""
set -euo pipefail
source {LIB}
rm() {{ echo "DELETED $*"; }}
fail=0
for target in / "$HOME" {ROOT} /Applications /tmp/not-a-stage; do
  if safe_remove_build_dir "$target" {ROOT} >/tmp/rs-stage-out 2>/tmp/rs-stage-err; then
    echo "accepted $target"
    fail=1
  fi
  if grep -q DELET ED /tmp/rs-stage-out 2>/dev/null; then
    echo "deleted $target"
    fail=1
  fi
done
link=$(mktemp -d /tmp/rs-holder-stage.XXXXXX)
ln -s "$link" /tmp/rs-stage-link
if safe_remove_build_dir /tmp/rs-stage-link {ROOT}; then
  echo accepted-symlink
  fail=1
fi
command rmdir "$link" || true
command rm -f /tmp/rs-stage-link
exit $fail
"""
        # The function name in the grep must not be split by the shell that runs us.
        script = script.replace("DELET ED", "DELETED")
        proc = subprocess.run(
            ["bash", "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("DELETED", proc.stdout)

    def test_stage_embeds_an_interpreter_and_refuses_install(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-runtime-src-") as td:
            source = Path(td) / "python3"
            source.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            source.chmod(0o755)
            canary = Path(td) / "do-not-delete"
            canary.mkdir()
            env = os.environ.copy()
            env["RS_HOLDER_STAGE_FIXTURES"] = "1"
            env["RS_HOLDER_RUNTIME_SOURCE"] = str(source)
            env["HOLDER_BUILD_DIR"] = str(canary)
            refused = subprocess.run(
                ["bash", str(STAGE), "stage"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )
            self.assertEqual(refused.returncode, 2, refused.stderr)
            self.assertTrue(canary.is_dir())
            env.pop("HOLDER_BUILD_DIR")
            staged = subprocess.run(
                ["bash", str(STAGE), "stage"],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            self.assertEqual(staged.returncode, 0, staged.stderr)
            embedded = ""
            for line in staged.stdout.splitlines():
                if line.startswith("EMBEDDED="):
                    embedded = line.split("=", 1)[1]
            self.assertTrue(embedded)
            self.assertTrue(Path(embedded).is_file())
            self.assertNotIn("/usr/bin/python3", embedded)
            self.assertIn("NOT_INSTALLED=1", staged.stdout)
            for command in ("install", "update", "rollback", "uninstall"):
                blocked = subprocess.run(
                    ["bash", str(STAGE), command],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=env,
                )
                self.assertEqual(blocked.returncode, 4, command)
                self.assertIn("was not run", blocked.stderr)

    def test_compiled_stage_is_adhoc_signed_and_not_installed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-runtime-src-") as td:
            source = Path(td) / "python3"
            source.write_bytes(Path("/tmp/rs-py312-rel-holder/bin/python").read_bytes())
            source.chmod(0o755)
            env = os.environ.copy()
            env["RS_HOLDER_STAGE_COMPILE"] = "1"
            env["RS_HOLDER_RUNTIME_SOURCE"] = str(source)
            env.pop("HOLDER_BUILD_DIR", None)
            staged = subprocess.run(
                ["bash", str(STAGE), "stage"],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(staged.returncode, 0, staged.stderr)
            app = ""
            for line in staged.stdout.splitlines():
                if line.startswith("STAGED="):
                    app = line.split("=", 1)[1]
            binary = Path(app) / "Contents/MacOS/RunSpecimenHolder"
            self.assertTrue(binary.is_file())
            kind = subprocess.run(["/usr/bin/file", str(binary)], capture_output=True, text=True, timeout=10)
            self.assertIn("Mach-O", kind.stdout)
            signed = subprocess.run(
                ["/usr/bin/codesign", "-dv", str(binary)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertIn("Signature=adhoc", signed.stderr)
            self.assertFalse(Path("/Applications/RunSpecimen Holder.app").joinpath("Contents/MacOS/RunSpecimenHolder").samefile(binary))
            self.assertIn("NOT_INSTALLED=1", staged.stdout)


class TrustOrderTests(unittest.TestCase):
    def test_pre_import_refuses_a_symlink_and_a_writable_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-preimport-") as td:
            root = Path(td) / "modules"
            package = root / "runspecimen"
            package.mkdir(parents=True)
            names = (
                "holder_daemon.py",
                "holder_entry.py",
                "holder_runtime.py",
                "execution_holder.py",
                "holder_asymmetric.py",
                "native_bridge.py",
            )
            for name in names:
                (package / name).write_text("# fixture\n", encoding="utf-8")
            validate_before_import(root)
            target = package / "holder_daemon.py"
            target.unlink()
            target.symlink_to(package / "holder_entry.py")
            with self.assertRaises(SystemExit) as sym:
                validate_before_import(root)
            self.assertIn("symlink", str(sym.exception))
            target.unlink()
            target.write_text("# fixture\n", encoding="utf-8")
            target.chmod(0o666)
            with self.assertRaises(SystemExit) as writable:
                validate_before_import(root)
            self.assertIn("writable", str(writable.exception))

    def test_secret_is_not_read_when_support_is_hostile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-support-") as td:
            support = Path(td) / "support"
            support.mkdir()
            support.chmod(0o777)
            with self.assertRaises(RuntimeTrustError) as ctx:
                assert_support_before_secret(support, env={})
            self.assertIn("world-writable", str(ctx.exception))
            support.chmod(0o755)
            state = support / "state"
            state.mkdir()
            state.chmod(0o700)
            assert_support_before_secret(support, env={})
            replacement = support / "replaced"
            replacement.write_text("real\n", encoding="utf-8")
            link = support / "link"
            link.symlink_to(replacement)
            with self.assertRaises(RuntimeTrustError) as linked:
                assert_support_before_secret(link, env={})
            self.assertIn("symlink", str(linked.exception))


class QualificationTests(unittest.TestCase):
    def test_verifier_architecture_is_arm64_when_present(self) -> None:
        binary = platform_verifier_binary()
        if binary is None or sys.platform != "darwin":
            self.assertIn(supported_verifier_architecture(binary), {"absent", "unverified"})
            return
        self.assertEqual(supported_verifier_architecture(binary), "arm64")

    def test_holder_state_is_not_world_readable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-qual-") as td:
            root = Path(td) / "state"
            holder = ExecutionHolder(root, allow_test_double=False, snapshot_base=Path(td) / "snaps")
            mode = stat.S_IMODE(root.stat().st_mode)
            self.assertEqual(mode & 0o077, 0)
            snap = stat.S_IMODE(holder.snapshot_base.stat().st_mode)
            self.assertEqual(snap & 0o006, 0)
            self.assertFalse((root / "enrollment.json").exists())
