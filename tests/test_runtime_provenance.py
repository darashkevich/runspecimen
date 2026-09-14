"""Tests for extended runtime provenance functionality."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from runspecimen.contract import Contract, RuntimeSpec, load_contract, parse_contract
from runspecimen.runtime import (
    _capture_env_allowlist,
    _detect_interpreter,
    _hash_env_allowlist,
    runtime_provenance,
)
from tests.helpers import PYTHON, base_contract, write_contract


class TestEnvAllowlist(unittest.TestCase):
    """Tests for environment variable capture."""

    def test_capture_set_variables(self):
        # Set some test variables
        os.environ["TEST_VAR_1"] = "value1"
        os.environ["TEST_VAR_2"] = "value2"

        try:
            result = _capture_env_allowlist(("TEST_VAR_1", "TEST_VAR_2"))

            self.assertEqual(result["TEST_VAR_1"], "value1")
            self.assertEqual(result["TEST_VAR_2"], "value2")
        finally:
            del os.environ["TEST_VAR_1"]
            del os.environ["TEST_VAR_2"]

    def test_capture_unset_variables_as_none(self):
        # Ensure variable doesn't exist
        if "UNSET_TEST_VAR" in os.environ:
            del os.environ["UNSET_TEST_VAR"]

        result = _capture_env_allowlist(("UNSET_TEST_VAR",))
        self.assertIsNone(result["UNSET_TEST_VAR"])

    def test_capture_is_sorted(self):
        os.environ["Z_VAR"] = "z"
        os.environ["A_VAR"] = "a"

        try:
            result = _capture_env_allowlist(("Z_VAR", "A_VAR"))
            keys = list(result.keys())
            self.assertEqual(keys, ["A_VAR", "Z_VAR"])
        finally:
            del os.environ["Z_VAR"]
            del os.environ["A_VAR"]

    def test_hash_env_is_deterministic(self):
        os.environ["DET_VAR"] = "same_value"

        try:
            capture1 = _capture_env_allowlist(("DET_VAR",))
            capture2 = _capture_env_allowlist(("DET_VAR",))

            hash1 = _hash_env_allowlist(capture1)
            hash2 = _hash_env_allowlist(capture2)

            self.assertEqual(hash1, hash2)
        finally:
            del os.environ["DET_VAR"]

    def test_hash_env_changes_with_value(self):
        os.environ["CHANGE_VAR"] = "value1"

        try:
            capture1 = _capture_env_allowlist(("CHANGE_VAR",))
            hash1 = _hash_env_allowlist(capture1)

            os.environ["CHANGE_VAR"] = "value2"
            capture2 = _capture_env_allowlist(("CHANGE_VAR",))
            hash2 = _hash_env_allowlist(capture2)

            self.assertNotEqual(hash1, hash2)
        finally:
            del os.environ["CHANGE_VAR"]


class TestInterpreterDetection(unittest.TestCase):
    """Tests for interpreter detection from shebang."""

    def test_detect_env_style_shebang(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("#!/usr/bin/env bash\necho hello\n")
            f.flush()
            script_path = Path(f.name)

        try:
            interpreter = _detect_interpreter(script_path)
            # Should find bash (or None if not in PATH)
            if interpreter:
                self.assertIn("bash", str(interpreter).lower())
        finally:
            script_path.unlink()

    def test_detect_direct_path_shebang(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("#!/bin/sh\necho hello\n")
            f.flush()
            script_path = Path(f.name)

        try:
            interpreter, args = _detect_interpreter(script_path)
            if interpreter and Path("/bin/sh").exists():
                # /bin/sh could be symlinked to dash, bash, etc.
                resolved = Path("/bin/sh").resolve()
                self.assertEqual(interpreter, resolved)
                self.assertEqual(args, [])
        finally:
            script_path.unlink()

    def test_detect_shebang_with_args(self):
        """Shebang args should be captured."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("#!/bin/sh -e\necho hello\n")
            f.flush()
            script_path = Path(f.name)

        try:
            interpreter, args = _detect_interpreter(script_path)
            if interpreter:
                self.assertEqual(args, ["-e"])
        finally:
            script_path.unlink()

    def test_detect_no_shebang_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("This is just text, no shebang\n")
            f.flush()
            file_path = Path(f.name)

        try:
            interpreter, args = _detect_interpreter(file_path)
            self.assertIsNone(interpreter)
            self.assertIsNone(args)
        finally:
            file_path.unlink()


class TestRuntimeSpecParsing(unittest.TestCase):
    """Tests for parsing runtime spec from contracts."""

    def test_contract_without_runtime_spec(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            doc = base_contract()
            contract_path = write_contract(workspace, "contract.json", doc)

            contract = load_contract(contract_path)
            self.assertIsNone(contract.runtime)

    def test_contract_with_env_allowlist(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            doc = base_contract()
            doc["runtime"] = {
                "env_allowlist": ["PATH", "HOME", "USER"],
            }
            contract_path = write_contract(workspace, "contract.json", doc)

            contract = load_contract(contract_path)
            self.assertIsNotNone(contract.runtime)
            self.assertEqual(contract.runtime.env_allowlist, ("PATH", "HOME", "USER"))

    def test_contract_with_interpreter(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            doc = base_contract()
            doc["runtime"] = {
                "interpreter": sys.executable,
                "env_allowlist": [],
            }
            contract_path = write_contract(workspace, "contract.json", doc)

            contract = load_contract(contract_path)
            self.assertIsNotNone(contract.runtime)
            self.assertEqual(contract.runtime.interpreter, sys.executable)

    def test_contract_with_capture_libs(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            doc = base_contract()
            doc["runtime"] = {
                "capture_libs": True,
                "env_allowlist": [],
            }
            contract_path = write_contract(workspace, "contract.json", doc)

            contract = load_contract(contract_path)
            self.assertIsNotNone(contract.runtime)
            self.assertTrue(contract.runtime.capture_libs)


class TestRuntimeProvenance(unittest.TestCase):
    """Tests for runtime provenance computation."""

    def test_provenance_includes_basic_fields(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            doc = base_contract()
            contract_path = write_contract(workspace, "contract.json", doc)
            contract = load_contract(contract_path)

            prov = runtime_provenance(contract, workspace)

            self.assertIn("argv0", prov)
            self.assertIn("resolved_executable", prov)
            self.assertIn("executable_sha256", prov)
            self.assertIn("runtime_id", prov)

    def test_provenance_includes_env_hash(self):
        """Environment variables should be recorded as hash only, not raw values."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            os.environ["TEST_PROV_VAR"] = "test_value"

            try:
                doc = base_contract()
                doc["runtime"] = {
                    "env_allowlist": ["TEST_PROV_VAR"],
                }
                contract_path = write_contract(workspace, "contract.json", doc)
                contract = load_contract(contract_path)

                prov = runtime_provenance(contract, workspace)

                self.assertIn("env_allowlist", prov)
                self.assertIn("env_hash", prov)
                # env_capture should NOT be present (security: no raw values)
                self.assertNotIn("env_capture", prov)
                self.assertEqual(prov["env_allowlist"], ["TEST_PROV_VAR"])
            finally:
                del os.environ["TEST_PROV_VAR"]

    def test_provenance_changes_with_env_change(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            os.environ["CHANGE_PROV_VAR"] = "original"

            try:
                doc = base_contract()
                doc["runtime"] = {
                    "env_allowlist": ["CHANGE_PROV_VAR"],
                }
                contract_path = write_contract(workspace, "contract.json", doc)
                contract = load_contract(contract_path)

                prov1 = runtime_provenance(contract, workspace)

                os.environ["CHANGE_PROV_VAR"] = "changed"
                prov2 = runtime_provenance(contract, workspace)

                self.assertNotEqual(prov1["runtime_id"], prov2["runtime_id"])
                self.assertNotEqual(prov1["env_hash"], prov2["env_hash"])
            finally:
                del os.environ["CHANGE_PROV_VAR"]

    def test_provenance_with_explicit_interpreter(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            doc = base_contract()
            doc["runtime"] = {
                "interpreter": sys.executable,
                "env_allowlist": [],
            }
            contract_path = write_contract(workspace, "contract.json", doc)
            contract = load_contract(contract_path)

            prov = runtime_provenance(contract, workspace)

            self.assertIn("interpreter", prov)
            self.assertIn("interpreter_sha256", prov)
            # The interpreter path gets resolved, so compare resolved paths
            self.assertEqual(
                Path(prov["interpreter"]).resolve(),
                Path(sys.executable).resolve()
            )


class TestEnvValueSecurity(unittest.TestCase):
    """Tests that raw env values are never persisted in evidence artifacts."""

    def test_sentinel_secret_absent_from_provenance(self):
        """A sentinel secret should NOT appear in runtime provenance."""
        import json

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            # Use a recognizable sentinel that we can search for
            sentinel = "RUNSPECIMEN_TEST_SENTINEL_DO_NOT_PERSIST"
            os.environ["SECRET_VAR"] = sentinel

            try:
                doc = base_contract()
                doc["runtime"] = {
                    "env_allowlist": ["SECRET_VAR"],
                }
                contract_path = write_contract(workspace, "contract.json", doc)
                contract = load_contract(contract_path)

                prov = runtime_provenance(contract, workspace)

                # Serialize the provenance and check for sentinel
                prov_json = json.dumps(prov)

                # The sentinel should NOT appear anywhere in the provenance
                self.assertNotIn(sentinel, prov_json)

                # Double check: env_capture should not be present
                self.assertNotIn("env_capture", prov)

                # But env_allowlist and env_hash should be
                self.assertIn("env_allowlist", prov)
                self.assertIn("env_hash", prov)
            finally:
                del os.environ["SECRET_VAR"]


class TestLddTrustSecurity(unittest.TestCase):
    """Tests that ldd is never invoked on untrusted/workspace binaries."""

    def test_capture_libs_does_not_execute_workspace_binary(self):
        """capture_libs must not invoke ldd on workspace/configured untrusted executables."""
        import platform

        # This test is only meaningful on Linux where ldd exists
        if platform.system() != "Linux":
            self.skipTest("ldd trust test only applicable on Linux")

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            # Create a workspace binary that would be dangerous to execute/inspect
            malicious_binary = workspace / "work" / "malicious_binary"
            malicious_binary.write_text("#!/bin/sh\necho EXECUTED\n", encoding="utf-8")
            malicious_binary.chmod(0o755)

            # Configure the contract to use this workspace binary as interpreter
            doc = base_contract()
            doc["runtime"] = {
                "interpreter": str(malicious_binary),
                "capture_libs": True,  # Request lib capture
                "env_allowlist": [],
            }
            contract_path = write_contract(workspace, "contract.json", doc)
            contract = load_contract(contract_path)

            prov = runtime_provenance(contract, workspace)

            # The provenance should report capture_libs_error because we
            # refuse to run ldd on untrusted workspace binaries
            self.assertIn("capture_libs_error", prov)
            self.assertIn("not verified as trusted", prov["capture_libs_error"].lower())
            # No libraries should be captured
            self.assertEqual(prov.get("lib_hashes", {}), {})

    def test_system_interpreter_is_trusted_for_capture_libs(self):
        """System interpreters in /usr, /bin, /opt are trusted for ldd."""
        import platform
        import shutil

        # This test is only meaningful on Linux where ldd exists
        if platform.system() != "Linux":
            self.skipTest("ldd trust test only applicable on Linux")

        # Find a real system interpreter
        python_path = shutil.which("python3") or shutil.which("python")
        if not python_path or not python_path.startswith(("/usr/", "/bin/", "/opt/")):
            self.skipTest("No system Python found in standard paths")

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            doc = base_contract()
            doc["runtime"] = {
                "interpreter": python_path,
                "capture_libs": True,
                "env_allowlist": [],
            }
            contract_path = write_contract(workspace, "contract.json", doc)
            contract = load_contract(contract_path)

            prov = runtime_provenance(contract, workspace)

            # Should NOT have capture_libs_error for system interpreter
            # (unless ldd itself isn't available)
            if "capture_libs_error" in prov:
                # If there's an error, it should be about ldd availability, not trust
                self.assertNotIn("not verified as trusted", prov["capture_libs_error"].lower())


class TestEnvSecretFullLifecycle(unittest.TestCase):
    """End-to-end tests that secrets are never persisted in any artifact."""

    def test_sentinel_absent_from_all_artifacts_after_full_lifecycle(self):
        """After full lifecycle, sentinel secret must not appear in any artifact."""
        from runspecimen.approve import approve_contract
        from runspecimen.preflight import preflight
        from runspecimen.run import run_contract
        from runspecimen.postflight import postflight
        from tests.helpers import PhraseReader, NullWriter
        import json
        import glob

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()

            # Create job script
            job = workspace / "work" / "job.py"
            job.write_text('''
import os
import json
result = {"env_val": os.environ.get("SECRET_VAR", "not-set")}
with open("outputs/out.json", "w") as f:
    json.dump(result, f)
''', encoding="utf-8")

            # Sentinel that must never appear in artifacts
            sentinel = "RUNSPECIMEN_LIFECYCLE_SECRET_ABC123"
            os.environ["SECRET_VAR"] = sentinel

            try:
                doc = base_contract()
                doc["argv"] = [sys.executable, "work/job.py"]
                doc["run_id"] = "secret-test"
                doc["runtime"] = {"env_allowlist": ["SECRET_VAR"]}
                # Simplify postflight - no json_equals assertions
                doc["postflight"]["json_equals"] = []
                contract_path = write_contract(workspace, "contract.json", doc)

                # Full lifecycle
                approve_contract(
                    contract_path=contract_path,
                    workspace=workspace,
                    skip_tty_check=True,
                    stdin=PhraseReader("APPROVE\n"),
                    stdout=NullWriter(),
                )
                preflight(contract_path=contract_path, workspace=workspace)
                run_contract(contract_path=contract_path, workspace=workspace)
                postflight(contract_path=contract_path, workspace=workspace)

                # Now scan ALL files in .runspecimen for the sentinel
                rs_dir = workspace / ".runspecimen"
                files_with_sentinel = []
                for path in rs_dir.rglob("*"):
                    if path.is_file():
                        try:
                            content = path.read_text(encoding="utf-8")
                            if sentinel in content:
                                files_with_sentinel.append(str(path))
                        except (UnicodeDecodeError, OSError):
                            # Binary file or unreadable
                            try:
                                content = path.read_bytes()
                                if sentinel.encode() in content:
                                    files_with_sentinel.append(str(path))
                            except OSError:
                                pass

                self.assertEqual(files_with_sentinel, [],
                    f"Sentinel secret found in artifacts: {files_with_sentinel}")
            finally:
                del os.environ["SECRET_VAR"]


class TestInterpreterLaunchVerification(unittest.TestCase):
    """End-to-end tests proving configured interpreter is actually used."""

    def test_configured_interpreter_is_invoked(self):
        """A configured interpreter must be the actual launch vector."""
        from runspecimen.approve import approve_contract
        from runspecimen.preflight import preflight
        from runspecimen.run import run_contract
        from runspecimen.state import load_state
        from tests.helpers import PhraseReader, NullWriter

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()

            # Create a script that outputs a marker showing which interpreter ran it
            script = workspace / "work" / "test_script.sh"
            script.write_text('#!/bin/sh\necho "MARKER_FROM_SCRIPT"\n', encoding="utf-8")
            script.chmod(0o755)

            # Create a wrapper interpreter that outputs its own marker
            wrapper = workspace / "work" / "wrapper_interp.sh"
            wrapper.write_text(
                '#!/bin/sh\necho "WRAPPER_INVOKED"\n# Run the actual script\nexec /bin/sh "$@"\n',
                encoding="utf-8"
            )
            wrapper.chmod(0o755)

            doc = base_contract()
            doc["argv"] = [str(script)]
            doc["run_id"] = "interp-test"
            doc["runtime"] = {
                "interpreter": str(wrapper),
            }
            doc["outputs"]["required"] = []
            doc["postflight"]["require_outputs"] = False
            contract_path = write_contract(workspace, "contract.json", doc)

            # Approve
            approve_contract(
                contract_path=contract_path,
                workspace=workspace,
                skip_tty_check=True,
                stdin=PhraseReader("APPROVE\n"),
                stdout=NullWriter(),
            )

            # Preflight
            preflight(contract_path=contract_path, workspace=workspace)

            # Run
            result = run_contract(contract_path=contract_path, workspace=workspace)

            # The wrapper interpreter should have been invoked
            stdout_capture = (
                workspace / ".runspecimen" / "runs" / doc["campaign_id"] / doc["run_id"] / "stdout.capture"
            )
            stdout_content = stdout_capture.read_text()

            self.assertIn("WRAPPER_INVOKED", stdout_content)
            self.assertIn("MARKER_FROM_SCRIPT", stdout_content)

    def test_missing_interpreter_fails_closed(self):
        """A configured interpreter that doesn't exist must fail approval."""
        from runspecimen.runtime import runtime_provenance
        from runspecimen.errors import ProvenanceError

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            script = workspace / "work" / "test.sh"
            script.write_text('#!/bin/sh\necho ok\n', encoding="utf-8")
            script.chmod(0o755)

            doc = base_contract()
            doc["argv"] = [str(script)]
            doc["runtime"] = {
                "interpreter": "/nonexistent/interpreter/path",
            }
            contract_path = write_contract(workspace, "contract.json", doc)
            contract = load_contract(contract_path)

            with self.assertRaises(ProvenanceError) as ctx:
                runtime_provenance(contract, workspace)
            self.assertIn("does not exist", str(ctx.exception))

    def test_non_executable_interpreter_fails_closed(self):
        """A configured interpreter without execute permission must fail."""
        from runspecimen.runtime import runtime_provenance
        from runspecimen.errors import ProvenanceError

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()

            script = workspace / "work" / "test.sh"
            script.write_text('#!/bin/sh\necho ok\n', encoding="utf-8")
            script.chmod(0o755)

            # Create a non-executable interpreter
            non_exec = workspace / "work" / "non_exec_interp"
            non_exec.write_text('#!/bin/sh\necho should not run\n', encoding="utf-8")
            non_exec.chmod(0o644)  # Not executable

            doc = base_contract()
            doc["argv"] = [str(script)]
            doc["runtime"] = {
                "interpreter": str(non_exec),
            }
            contract_path = write_contract(workspace, "contract.json", doc)
            contract = load_contract(contract_path)

            with self.assertRaises(ProvenanceError) as ctx:
                runtime_provenance(contract, workspace)
            self.assertIn("not executable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
