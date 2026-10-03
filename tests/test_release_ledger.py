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
        if not Path("/usr/bin/xcrun").is_file():
            self.skipTest("swiftc is not on this runner")
        with tempfile.TemporaryDirectory(prefix="rs-runtime-src-") as td:
            source = Path(td) / "python3"
            source.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
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
            live = Path("/Applications/RunSpecimen Holder.app/Contents/MacOS/RunSpecimenHolder")
            if live.exists():
                self.assertFalse(live.samefile(binary))
            self.assertIn("NOT_INSTALLED=1", staged.stdout)

    def _live_mtimes(self) -> dict[str, int | None]:
        found = {}
        for path in (
            "/Applications/RunSpecimen.app",
            "/Applications/RunSpecimen Holder.app",
        ):
            candidate = Path(path)
            found[path] = candidate.stat().st_mtime_ns if candidate.exists() else None
        return found

    def _stage(self, env: dict[str, str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(STAGE), "stage"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

    def _field(self, completed: subprocess.CompletedProcess[str], name: str) -> str:
        for line in completed.stdout.splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1]
        self.fail(f"missing {name} in {completed.stdout}")
        return ""

    def test_fixture_lifecycle_stays_in_a_temp_root(self) -> None:
        before = self._live_mtimes()
        with tempfile.TemporaryDirectory(prefix="rs-runtime-src-") as td:
            source = Path(td) / "python3"
            source.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            source.chmod(0o755)
            env = os.environ.copy()
            env["RS_HOLDER_STAGE_FIXTURES"] = "1"
            env["RS_HOLDER_RUNTIME_SOURCE"] = str(source)
            env.pop("HOLDER_BUILD_DIR", None)
            staged = self._stage(env)
            self.assertEqual(staged.returncode, 0, staged.stderr)
            app = self._field(staged, "STAGED")
            plist = Path(self._field(staged, "PLIST"))
            self.assertTrue(plist.is_file())
            self.assertIn("Contents/MacOS/RunSpecimenHolderDaemon", plist.read_text(encoding="utf-8"))
            self.assertTrue((Path(app) / "Contents/MacOS/RunSpecimenHolderDaemon").is_file())
            info = (Path(app) / "Contents/Info.plist").read_text(encoding="utf-8")
            self.assertIn("RunSpecimenHolder", info)
            self.assertNotEqual(Path(self._field(staged, "EMBEDDED")).resolve(), Path("/usr/bin/python3"))
            blocked = subprocess.run(
                ["bash", str(STAGE), "install"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )
            self.assertEqual(blocked.returncode, 4)
            self.assertIn("was not run", blocked.stderr)
            env["RS_HOLDER_INSTALL_CONSENT"] = "yes"
            env["RS_HOLDER_PACKAGE"] = app
            env["RS_HOLDER_INSTALL_ROOT"] = "/Applications"
            refused = subprocess.run(
                ["bash", str(STAGE), "install"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )
            self.assertEqual(refused.returncode, 4, refused.stderr)
            self.assertIn("was not run", refused.stderr)
            with tempfile.TemporaryDirectory(prefix="rs-holder-root-", dir="/tmp") as root:
                env["RS_HOLDER_INSTALL_ROOT"] = root
                installed = subprocess.run(
                    ["bash", str(STAGE), "install"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=env,
                )
                self.assertEqual(installed.returncode, 0, installed.stderr)
                dest = Path(root) / "RunSpecimen Holder.app"
                self.assertTrue(dest.is_dir())
                marker = dest / "Contents/Resources/generation.txt"
                marker.write_text("v1\n", encoding="utf-8")
                updated = subprocess.run(
                    ["bash", str(STAGE), "update"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=env,
                )
                self.assertEqual(updated.returncode, 0, updated.stderr)
                self.assertFalse(marker.exists())
                saved = Path(root) / "rollback" / "RunSpecimen Holder.app" / "Contents/Resources/generation.txt"
                self.assertEqual(saved.read_text(encoding="utf-8"), "v1\n")
                rolled = subprocess.run(
                    ["bash", str(STAGE), "rollback"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=env,
                )
                self.assertEqual(rolled.returncode, 0, rolled.stderr)
                self.assertEqual(marker.read_text(encoding="utf-8"), "v1\n")
                removed = subprocess.run(
                    ["bash", str(STAGE), "uninstall"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=env,
                )
                self.assertEqual(removed.returncode, 0, removed.stderr)
                self.assertFalse(dest.exists())
                self.assertTrue((Path(root) / "removed" / "RunSpecimen Holder.app").is_dir())
        self.assertEqual(self._live_mtimes(), before)

    def test_compiled_package_relocates_runtime_without_a_developer_interpreter(self) -> None:
        if sys.platform != "darwin" or not Path("/usr/bin/otool").is_file() or not Path("/usr/bin/xcrun").is_file():
            self.skipTest("relocatable Mach-O staging is macOS-only")
        source_exec = Path(sys.executable).resolve()
        if source_exec == Path("/usr/bin/python3"):
            self.skipTest("refusing /usr/bin/python3 as the payload interpreter")
        kind = subprocess.run(["/usr/bin/file", "-b", str(source_exec)], capture_output=True, text=True, timeout=10)
        if "Mach-O" not in kind.stdout:
            self.skipTest("the test interpreter is not a Mach-O payload")
        before = self._live_mtimes()
        with tempfile.TemporaryDirectory(prefix="rs-runtime-src-") as td:
            source = Path(td) / "python3"
            subprocess.run(["/bin/cp", "-p", str(source_exec), str(source)], check=True, timeout=20)
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["RS_HOLDER_STAGE_COMPILE"] = "1"
            env["RS_HOLDER_RUNTIME_SOURCE"] = str(source)
            env["RS_HOLDER_BUNDLE_RUNNER"] = sys.executable
            env.pop("HOLDER_BUILD_DIR", None)
            staged = self._stage(env, timeout=180)
            self.assertEqual(staged.returncode, 0, staged.stderr)
            app = Path(self._field(staged, "STAGED"))
            embedded = Path(self._field(staged, "EMBEDDED"))
            ui = Path(self._field(staged, "UI"))
            daemon = Path(self._field(staged, "DAEMON"))
            plist = Path(self._field(staged, "PLIST"))
            self.assertNotEqual(embedded.resolve(), Path("/usr/bin/python3"))
            self.assertFalse(ui.samefile(daemon))
            for binary in (ui, daemon, embedded):
                described = subprocess.run(["/usr/bin/file", "-b", str(binary)], capture_output=True, text=True, timeout=10)
                self.assertIn("Mach-O", described.stdout, binary)
            linked = subprocess.run(["/usr/bin/otool", "-L", str(embedded)], capture_output=True, text=True, timeout=10)
            self.assertNotIn("/opt/homebrew", linked.stdout)
            self.assertNotIn("/usr/local", linked.stdout)
            self.assertNotIn("/usr/bin/python3", linked.stdout)
            listed = plist.read_text(encoding="utf-8")
            self.assertIn("Contents/MacOS/RunSpecimenHolderDaemon", listed)
            self.assertTrue(daemon.is_file())
            info = (app / "Contents/Info.plist").read_text(encoding="utf-8")
            self.assertIn("<string>RunSpecimenHolder</string>", info)
            named = subprocess.run(["/usr/bin/strings", str(ui)], capture_output=True, text=True, timeout=20)
            self.assertIn("com.darashkevich.runspecimen.holder.daemon.plist", named.stdout)
            runtime = embedded.parent.parent
            probe_env = os.environ.copy()
            probe_env.pop("PYTHONPATH", None)
            probe_env["PYTHONHOME"] = str(runtime)
            probe_env["PYTHONNOUSERSITE"] = "1"
            probed = subprocess.run(
                [str(embedded), "-c", "import encodings,sys\nprint(sys.prefix)\nprint(encodings.__file__)\n"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=probe_env,
            )
            self.assertEqual(probed.returncode, 0, probed.stderr)
            prefix, encodings = [line.strip() for line in probed.stdout.splitlines() if line.strip()]
            self.assertEqual(Path(prefix).resolve(), runtime.resolve())
            self.assertTrue(Path(encodings).resolve().is_relative_to(runtime.resolve()))
            self.assertNotIn("/opt/homebrew", encodings)
            self.assertNotIn("/usr/bin/python3", encodings)
            daemon_text = (ROOT / "apps/holder/Sources/RunSpecimenHolderDaemon/main.swift").read_text(encoding="utf-8")
            self.assertIn('getenv("PYTHONPATH")', daemon_text)
            self.assertIn('getenv("PYTHONHOME")', daemon_text)
            self.assertIn('setenv("PYTHONHOME"', daemon_text)
            self.assertNotIn('"-I"', daemon_text)
            self.assertNotIn('"/usr/bin/python3"', daemon_text)
        self.assertEqual(self._live_mtimes(), before)

    def test_detached_interpreter_is_not_executed(self) -> None:
        if sys.platform != "darwin" or not Path("/usr/bin/otool").is_file():
            self.skipTest("relocatable Mach-O staging is macOS-only")
        source_exec = Path(sys.executable).resolve()
        if source_exec == Path("/usr/bin/python3"):
            self.skipTest("refusing /usr/bin/python3 as the payload interpreter")
        kind = subprocess.run(["/usr/bin/file", "-b", str(source_exec)], capture_output=True, text=True, timeout=10)
        if "Mach-O" not in kind.stdout:
            self.skipTest("the test interpreter is not a Mach-O payload")
        with tempfile.TemporaryDirectory(prefix="rs-runtime-detached-") as td:
            source = Path(td) / "python3"
            subprocess.run(["/bin/cp", "-p", str(source_exec), str(source)], check=True, timeout=20)
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env.pop("RS_HOLDER_BUNDLE_RUNNER", None)
            env["RS_HOLDER_STAGE_FIXTURES"] = "1"
            env["RS_HOLDER_RUNTIME_SOURCE"] = str(source)
            env.pop("HOLDER_BUILD_DIR", None)
            staged = self._stage(env, timeout=30)
            self.assertEqual(staged.returncode, 2, staged.stderr)
            self.assertNotEqual(staged.returncode, 134)
            self.assertIn("was not executed", staged.stderr)

    def test_dependency_cycles_and_collisions_are_bounded(self) -> None:
        import importlib.util

        path = ROOT / "apps/holder/Scripts/bundle_runtime.py"
        spec = importlib.util.spec_from_file_location("bundle_runtime_under_test", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cycle = module.plan_external_copies(
            ["root"],
            lambda node: {"root": ["a"], "a": ["b"], "b": ["a", "b"]}.get(node, []),
            inside_dest=lambda _node: False,
            max_nodes=8,
        )
        self.assertEqual(sorted(cycle), ["a", "b"])
        collided = module.plan_external_copies(
            ["root"],
            lambda node: {
                "root": ["/lib/foo.dylib", "/other/foo.dylib"],
                "/lib/foo.dylib": ["/other/foo.dylib"],
                "/other/foo.dylib": ["/lib/foo.dylib"],
            }.get(node, []),
            inside_dest=lambda node: node.startswith("/staged"),
            max_nodes=8,
        )
        self.assertEqual(len(collided), 2)
        self.assertIn("foo.dylib", collided)
        self.assertTrue(any(name != "foo.dylib" and "-" in name for name in collided))
        self.assertFalse(any(name.startswith("lib-lib") for name in collided))
        self.assertTrue(all(len(name) < 80 for name in collided))
        staged = module.plan_external_copies(
            ["root"],
            lambda node: {
                "root": ["root", "/staged/lib/already.so", "ext.so"],
                "ext.so": ["/staged/lib/already.so", "ext.so"],
            }.get(node, []),
            inside_dest=lambda node: str(node).startswith("/staged"),
            max_nodes=8,
        )
        self.assertEqual(staged, ["ext.so"])
        chain = {f"n{index}": [f"n{index + 1}"] for index in range(20)}
        chain["root"] = ["n0"]
        from contextlib import redirect_stderr
        from io import StringIO

        buffer = StringIO()
        with redirect_stderr(buffer):
            with self.assertRaises(SystemExit) as bounded:
                module.plan_external_copies(
                    ["root"],
                    lambda node: chain.get(node, []),
                    inside_dest=lambda _node: False,
                    max_nodes=4,
                )
        self.assertEqual(bounded.exception.code, 2)
        self.assertIn("exceeded the staged library bound", buffer.getvalue())


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
