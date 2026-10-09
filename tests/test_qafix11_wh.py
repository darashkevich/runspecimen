"""WH-01..WH-04 regressions for unpublished 0.2.0rc15 qafix11."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import (
    PYTHON,
    ROOT,
    SRC,
    RunSpecimenTestCase,
    approve,
    base_contract,
    write_contract,
)
from tests.test_qafix11_cc import BIDI, BS, CSI, CR, ESC, NUL, OSC, _prompt
from tests.test_rc15_qafix_docs import (
    VERIFY_INSTALLED,
    _create_venv_and_install,
    _install_and_verify,
    _load_verify_module,
    _pin_wheel,
    _sanitized_env,
    _venv_launcher,
)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.cli import main
from runspecimen.configsync import loaded_module_origins
from runspecimen.contract import load_contract
from runspecimen.errors import ContractError, PathEscapeError, PreflightError, RunError
from runspecimen.paths import CONTROL_PLANE_SYMLINK_REFUSAL, assert_control_plane_not_symlinked
from runspecimen.present import (
    APPROVE_BIND_PROMPT,
    escape_for_terminal,
    format_error,
    format_pretty,
)
from runspecimen.run import run_contract
from runspecimen.runtime import ALLOWLIST_ENV_DRIFT, MINIMAL_JOB_ENV_NAMES, job_environment


class WH01StdlibShadowingTests(unittest.TestCase):
    def test_wh01_bin_json_py_is_refused(self) -> None:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")

        def plant_json(hook: object) -> None:
            bin_dir = Path(hook.launcher).parent  # type: ignore[attr-defined]
            (bin_dir / "json.py").write_text("steal = True\n", encoding="utf-8")

        result = _install_and_verify(pin, pin, after_install=plant_json)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        combined = result.stdout + result.stderr
        self.assertTrue(
            "json.py" in combined or "venv bin" in combined,
            combined,
        )

    def test_wh01_bin_allowlist_includes_versioned_python_and_pip(self) -> None:
        module = _load_verify_module()
        self.assertTrue(module.is_allowed_venv_bin_name("python3.14"))
        self.assertTrue(module.is_allowed_venv_bin_name("python3.13"))
        self.assertTrue(module.is_allowed_venv_bin_name("pip3.14"))
        self.assertTrue(module.is_allowed_venv_bin_name("python3.14t"))
        self.assertFalse(module.is_allowed_venv_bin_name("json.py"))
        self.assertFalse(module.is_allowed_venv_bin_name("pythonw.sh"))

    def test_wh01_bin_directory_and_pyc_are_refused(self) -> None:
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-wh01-bin-") as raw:
            bin_dir = Path(raw)
            (bin_dir / "python").write_text("", encoding="utf-8")
            (bin_dir / "__pycache__").mkdir()
            (bin_dir / "re.pyc").write_bytes(b"\0")
            findings = module.scan_venv_bin(bin_dir)
            joined = " ".join(findings)
            self.assertIn("__pycache__", joined)
            self.assertIn("re.pyc", joined)

    def test_wh01_doctor_json_includes_loaded_module_origins(self) -> None:
        import contextlib
        import io

        out = io.StringIO()
        err = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="rs-wh01-doctor-") as raw:
            ws = Path(raw)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["doctor", "--workspace", str(ws)])
        self.assertEqual(code, 0, err.getvalue())
        doc = json.loads(out.getvalue())
        origins = doc["loaded_module_origins"]
        self.assertIsInstance(origins, dict)
        self.assertIn("runspecimen", origins)
        self.assertIn("json", origins)
        json_origin = origins["json"]
        self.assertTrue(json_origin)
        self.assertFalse(str(json_origin).replace("\\", "/").endswith("/bin/json.py"))
        rs_origin = str(origins["runspecimen"])
        self.assertTrue(
            rs_origin.endswith("runspecimen/__init__.py")
            or rs_origin.endswith("runspecimen\\__init__.py")
        )

    def test_wh01_loaded_module_origins_helper_uses_realpaths(self) -> None:
        origins = loaded_module_origins()
        self.assertIn("json", origins)
        self.assertEqual(Path(str(origins["json"])).resolve(), Path(str(origins["json"])))

    def test_wh01_doctor_origin_allowlist_accepts_launcher_main_and_distro_sitecustomize(self) -> None:
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-wh01-origins-") as raw:
            host = Path(raw)
            venv = host / "venv"
            stdlib = host / "lib" / "python"
            (stdlib / "json").mkdir(parents=True)
            json_init = stdlib / "json" / "__init__.py"
            json_init.write_text("", encoding="utf-8")
            launcher = venv / "bin" / "runspecimen"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("#!/usr/bin/python3\n", encoding="utf-8")
            hashed = venv / "lib" / "python" / "site-packages" / "runspecimen" / "__init__.py"
            hashed.parent.mkdir(parents=True)
            hashed.write_text("", encoding="utf-8")
            planted = launcher.parent / "json.py"
            planted.write_text("steal = True\n", encoding="utf-8")
            distro = host / "etc" / "python3.12" / "sitecustomize.py"
            distro.parent.mkdir(parents=True)
            distro.write_text("", encoding="utf-8")
            evil = hashed.parent.parent / "evil.py"
            evil.write_text("x = 1\n", encoding="utf-8")
            ok = module.launcher_module_origin_findings(
                {
                    "json": str(json_init),
                    "runspecimen": str(hashed),
                    "__main__": str(launcher),
                    "sitecustomize": str(distro),
                },
                stdlib_roots=[stdlib],
                hashed_files={hashed},
                launcher=launcher,
                venv_prefix=venv,
            )
            self.assertEqual(ok, [])
            bad = module.launcher_module_origin_findings(
                {"json": str(planted)},
                stdlib_roots=[stdlib],
                hashed_files={hashed},
                launcher=launcher,
                venv_prefix=venv,
            )
            self.assertTrue(any("json" in item for item in bad), bad)
            extra = module.launcher_module_origin_findings(
                {"evil": str(evil)},
                stdlib_roots=[stdlib],
                hashed_files={hashed},
                launcher=launcher,
                venv_prefix=venv,
            )
            self.assertTrue(any("evil" in item for item in extra), extra)


class WH02DisplaySanitizationTests(unittest.TestCase):
    def test_wh02_require_str_refuses_controls_with_plain_english(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-wh02-req-") as raw:
            ws = Path(raw)
            (ws / "work").mkdir()
            path = write_contract(ws, "bad.json", base_contract(cwd=f"./{CR}here"))
            with self.assertRaises(ContractError) as ctx:
                load_contract(path)
            msg = str(ctx.exception)
            self.assertIn("must not contain terminal control or invisible format characters", msg)
            self.assertNotIn(CR, msg)

    def test_wh02_approve_cwd_outputs_escape_cr_osc_csi(self) -> None:
        raw = _prompt(cwd=f".{CR}dir", outputs=[f"out{OSC}.json"]).encode("utf-8")
        self.assertNotIn(CR.encode("utf-8"), raw)
        self.assertNotIn(OSC.encode("utf-8"), raw)
        self.assertIn(escape_for_terminal(CR).encode("utf-8"), raw)
        self.assertTrue(raw.endswith(APPROVE_BIND_PROMPT.encode("utf-8")) or APPROVE_BIND_PROMPT.encode("utf-8") in raw)

    def test_wh02_pretty_error_status_doctor_confirm_note_escape(self) -> None:
        err = format_error(f"boom{CSI}{BS}", pretty=True, color_mode="never").encode("utf-8")
        self.assertNotIn(CSI.encode("utf-8"), err)
        self.assertNotIn(BS.encode("utf-8"), err)

        status = format_pretty(
            {
                "phase": "approved",
                "workspace": f"/tmp{CR}ws",
                "campaign_id": f"camp{OSC}",
                "run_id": f"run{BIDI}",
                "event_chain_msg": f"ok{ESC}",
            },
            kind="status",
            color_mode="never",
        ).encode("utf-8")
        self.assertNotIn(CR.encode("utf-8"), status)
        self.assertNotIn(OSC.encode("utf-8"), status)
        self.assertNotIn(BIDI.encode("utf-8"), status)
        self.assertNotIn(ESC.encode("utf-8"), status)

        doctor = format_pretty(
            {
                "ok": True,
                "workspace": f"/tmp{CSI}/ws",
                "platform": f"linux{CR}",
                "python": "3.12",
            },
            kind="doctor",
            color_mode="never",
        ).encode("utf-8")
        self.assertNotIn(CSI.encode("utf-8"), doctor)
        self.assertNotIn(CR.encode("utf-8"), doctor)

        note = format_pretty(
            {
                "ok": True,
                "confirm_channel": "remote_human_confirm",
                "confirm_channel_note": f"Remote{CR}FAKE-OK  run xyz",
            },
            kind="verify",
            color_mode="never",
        ).encode("utf-8")
        self.assertNotIn(CR.encode("utf-8"), note)
        self.assertIn(escape_for_terminal(CR).encode("utf-8"), note)

    def test_wh02_nul_still_refused_at_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-wh02-nul-") as raw:
            ws = Path(raw)
            (ws / "work").mkdir()
            path = write_contract(ws, "nul.json", base_contract(argv=[PYTHON, f"x{NUL}y"]))
            with self.assertRaises(ContractError) as ctx:
                load_contract(path)
            self.assertIn("NUL", str(ctx.exception))


class WH03BoundJobEnvironmentTests(RunSpecimenTestCase):
    def test_wh03_parent_pythonpath_does_not_reach_the_job(self) -> None:
        job = (
            "import json, os\n"
            "from pathlib import Path\n"
            "Path('outputs/out.json').write_text(json.dumps({\n"
            "    'status': 'ok',\n"
            "    'pythonpath': os.environ.get('PYTHONPATH'),\n"
            "    'pythonhome': os.environ.get('PYTHONHOME'),\n"
            "}) + '\\n', encoding='utf-8')\n"
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
        path = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, path)
        with patch.dict(os.environ, {"PYTHONPATH": "/tmp/evil-path", "PYTHONHOME": "/tmp/evil-home"}):
            result = run_contract(contract_path=path, workspace=self.ws)
        self.assertEqual(result["exit_code"], 0)
        payload = json.loads((self.ws / "outputs" / "out.json").read_text(encoding="utf-8"))
        self.assertIsNone(payload["pythonpath"])
        self.assertIsNone(payload["pythonhome"])

    def test_wh03_allowlisted_env_drift_is_refused(self) -> None:
        path = write_contract(
            self.ws,
            "contract.json",
            base_contract(runtime={"env_allowlist": ["RS_WH03_BOUND"]}),
        )
        os.environ["RS_WH03_BOUND"] = "alpha"
        try:
            approve(self.ws, path)
            os.environ["RS_WH03_BOUND"] = "beta"
            with self.assertRaises(PreflightError) as ctx:
                run_contract(contract_path=path, workspace=self.ws)
            msg = str(ctx.exception)
            self.assertTrue(
                msg == ALLOWLIST_ENV_DRIFT or "environment variables changed" in msg,
                msg,
            )
        finally:
            os.environ.pop("RS_WH03_BOUND", None)

    def test_wh03_job_environment_refuses_hash_drift(self) -> None:
        path = write_contract(
            self.ws,
            "contract.json",
            base_contract(runtime={"env_allowlist": ["RS_WH03_JOBENV"]}),
        )
        os.environ["RS_WH03_JOBENV"] = "alpha"
        try:
            from runspecimen.contract import load_contract as _load
            from runspecimen.runtime import _capture_env_allowlist, _hash_env_allowlist

            contract = _load(path)
            bound_hash = _hash_env_allowlist(_capture_env_allowlist(("RS_WH03_JOBENV",)))
            os.environ["RS_WH03_JOBENV"] = "beta"
            with self.assertRaises(RunError) as ctx:
                job_environment(contract, {"env_hash": bound_hash})
            self.assertEqual(str(ctx.exception), ALLOWLIST_ENV_DRIFT)
        finally:
            os.environ.pop("RS_WH03_JOBENV", None)

    def test_wh03_allowlisted_value_is_passed_and_python_star_not_in_minimal_set(self) -> None:
        self.assertNotIn("PYTHONPATH", MINIMAL_JOB_ENV_NAMES)
        self.assertNotIn("PYTHONHOME", MINIMAL_JOB_ENV_NAMES)
        path = write_contract(
            self.ws,
            "contract.json",
            base_contract(runtime={"env_allowlist": ["RS_WH03_KEEP"]}),
        )
        os.environ["RS_WH03_KEEP"] = "bound-value"
        try:
            approve(self.ws, path)
            from runspecimen.contract import load_contract as _load
            from runspecimen.approve import load_approval
            from runspecimen.paths import run_state_dir

            contract = _load(path)
            approval = load_approval(run_state_dir(self.ws, contract.campaign_id, contract.run_id))
            env = job_environment(contract, approval["runtime"] if approval else {})
            self.assertEqual(env.get("RS_WH03_KEEP"), "bound-value")
            self.assertNotIn("PYTHONPATH", env)
        finally:
            os.environ.pop("RS_WH03_KEEP", None)


class WH04ControlPlaneSymlinkTests(RunSpecimenTestCase):
    def test_wh04_symlinked_runspecimen_is_refused_on_approve(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="rs-wh04-out-"))
        try:
            (self.ws / ".runspecimen").symlink_to(outside)
            path = write_contract(self.ws, "contract.json", base_contract())
            with self.assertRaises(PathEscapeError) as ctx:
                approve(self.ws, path)
            self.assertIn("symlink", str(ctx.exception).lower())
            self.assertIn(CONTROL_PLANE_SYMLINK_REFUSAL.split("(")[0].strip(), str(ctx.exception))
            self.assertFalse((outside / "runs").exists())
        finally:
            import shutil

            shutil.rmtree(outside, ignore_errors=True)

    def test_wh04_symlinked_run_dir_is_refused(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="rs-wh04-run-"))
        try:
            control = self.ws / ".runspecimen" / "runs" / "camp"
            control.mkdir(parents=True)
            (control / "run-a").symlink_to(outside)
            with self.assertRaises(PathEscapeError):
                assert_control_plane_not_symlinked(control / "run-a")
        finally:
            import shutil

            shutil.rmtree(outside, ignore_errors=True)

    def test_wh04_symlinked_campaign_dir_is_refused_on_run_state(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="rs-wh04-camp-"))
        try:
            runs = self.ws / ".runspecimen" / "runs"
            runs.mkdir(parents=True)
            (runs / "camp").symlink_to(outside)
            path = write_contract(self.ws, "contract.json", base_contract())
            with self.assertRaises(PathEscapeError):
                approve(self.ws, path)
        finally:
            import shutil

            shutil.rmtree(outside, ignore_errors=True)


class WH01DocsNeverMinusMTests(unittest.TestCase):
    def test_wh01_human_acceptance_does_not_invoke_minus_m_runspecimen(self) -> None:
        from tests.test_rc15_qafix_docs import _bash_commands

        text = (ROOT / "docs" / "HUMAN-ACCEPTANCE.md").read_text(encoding="utf-8")
        self.assertIn("not a supported verified", text)
        self.assertIn("path; this sheet only invokes the absolute launcher", text)
        self.assertIn("untrusted cwd", text.lower())
        self.assertIn("$RS", text)
        for command in _bash_commands(text):
            self.assertNotIn("-m runspecimen", command)
            self.assertNotRegex(command, r"\bpython3?\s+-m\s+runspecimen\b")


if __name__ == "__main__":
    unittest.main()
