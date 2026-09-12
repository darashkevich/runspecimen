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
            interpreter = _detect_interpreter(script_path)
            if interpreter and Path("/bin/sh").exists():
                # /bin/sh could be symlinked to dash, bash, etc.
                resolved = Path("/bin/sh").resolve()
                self.assertEqual(interpreter, resolved)
        finally:
            script_path.unlink()

    def test_detect_no_shebang_returns_none(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("This is just text, no shebang\n")
            f.flush()
            file_path = Path(f.name)
        
        try:
            result = _detect_interpreter(file_path)
            self.assertIsNone(result)
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

    def test_provenance_includes_env_capture(self):
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
                self.assertIn("env_capture", prov)
                self.assertIn("env_hash", prov)
                self.assertEqual(prov["env_capture"]["TEST_PROV_VAR"], "test_value")
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


if __name__ == "__main__":
    unittest.main()
