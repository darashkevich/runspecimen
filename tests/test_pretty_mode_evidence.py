"""Default JSON bytes vs qafix4 / 5565000, plus pretty-mode exit parity."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path

from tests.helpers import PYTHON, ROOT, base_contract, write_contract


QAFIX4_PACK = ROOT / "artifacts" / "0.2.0rc15-2026-10-08-qafix4"
WHEEL_NAME = "runspecimen-0.2.0rc15-py3-none-any.whl"
QAFIX4_WHEEL_SHA256 = (
    "bd9e6520160b103b96e71762e562b9b8a8f8798e15cb36b200de038c490d46c4"
)
N10_LINE = "RunSpecimen error: execution policy local has no typed-phrase fallback"


def _sanitized_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONSTARTUP", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _venv_launcher(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "runspecimen.exe"
    return venv_dir / "bin" / "runspecimen"


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _install_wheel(venv_dir: Path, wheel: Path) -> Path:
    if venv_dir.exists():
        raise AssertionError(f"venv target already exists: {venv_dir}")
    venv.create(venv_dir, with_pip=True, symlinks=True)
    py = _venv_python(venv_dir)
    env = _sanitized_env()
    install = subprocess.run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            str(wheel.resolve()),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if install.returncode != 0:
        raise AssertionError(f"pip install failed: {install.stderr}")
    return _venv_launcher(venv_dir)


def _wheel_current_tree(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    env = _sanitized_env()
    result = subprocess.run(
        [
            PYTHON,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(dest),
            str(ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise AssertionError(f"pip wheel failed: {result.stdout}\n{result.stderr}")
    wheels = list(dest.glob("runspecimen-0.2.0rc15-*.whl"))
    if len(wheels) != 1:
        raise AssertionError(f"expected one current wheel, got {wheels}")
    return wheels[0]


def _run_rs(launcher: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = _sanitized_env()
    return subprocess.run(
        [str(launcher), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
    )


class TestPrettyModeEvidence(unittest.TestCase):
    def test_default_json_matches_qafix4_5565000_for_covered_commands(self) -> None:
        baseline_wheel = QAFIX4_PACK / WHEEL_NAME
        if not baseline_wheel.is_file():
            self.skipTest("qafix4 wheel must be on disk for 5565000 byte compare")
        import hashlib

        self.assertEqual(
            hashlib.sha256(baseline_wheel.read_bytes()).hexdigest(),
            QAFIX4_WHEEL_SHA256,
        )
        with tempfile.TemporaryDirectory(prefix="rs-pretty-ev-") as raw:
            root = Path(raw)
            ws = root / "ws"
            ws.mkdir()
            (ws / "work").mkdir()
            (ws / "outputs").mkdir()
            (ws / "work" / "job.py").write_text("print('ok')\n", encoding="utf-8")
            ordinary = write_contract(ws, "ordinary.json", base_contract())
            unknown = write_contract(
                ws,
                "unknown.json",
                {**base_contract(), "not_a_real_contract_field": True},
            )
            local = write_contract(
                ws, "local.json", base_contract(execution_approval="local")
            )
            companion = write_contract(
                ws, "companion.json", base_contract(execution_approval="companion")
            )
            dual = write_contract(
                ws, "dual.json", base_contract(execution_approval="dual")
            )

            base_venv = root / "base"
            cur_venv = root / "cur"
            base_rs = _install_wheel(base_venv, baseline_wheel)
            current_wheel = _wheel_current_tree(root / "cur-wheel")
            cur_rs = _install_wheel(cur_venv, current_wheel)

            # about JSON is the documented qafix10 exception (honesty wording).
            # Every other covered command stays byte-exact vs qafix4 / 5565000.
            commands: list[tuple[str, list[str]]] = [
                (
                    "missing-contract",
                    [
                        "validate",
                        "--workspace",
                        str(ws),
                        "--contract",
                        str(ws / "missing.json"),
                    ],
                ),
                (
                    "unknown-field",
                    ["validate", "--workspace", str(ws), "--contract", str(unknown)],
                ),
                (
                    "n10-local",
                    ["approve", "--workspace", str(ws), "--contract", str(local)],
                ),
                (
                    "n10-companion",
                    ["approve", "--workspace", str(ws), "--contract", str(companion)],
                ),
                (
                    "n10-dual",
                    ["approve", "--workspace", str(ws), "--contract", str(dual)],
                ),
            ]
            del ordinary
            for name, argv in commands:
                with self.subTest(command=name, mode="default"):
                    left = _run_rs(base_rs, argv, ws)
                    right = _run_rs(cur_rs, argv, ws)
                    self.assertEqual(left.returncode, right.returncode, name)
                    self.assertEqual(left.stdout, right.stdout, name)
                    self.assertEqual(left.stderr, right.stderr, name)
                with self.subTest(command=name, mode="pretty"):
                    pretty = _run_rs(cur_rs, ["--pretty", "--color", "never", *argv], ws)
                    default = _run_rs(cur_rs, argv, ws)
                    self.assertEqual(pretty.returncode, default.returncode, name)
                    if pretty.returncode == 0 and default.stdout:
                        with self.assertRaises(json.JSONDecodeError):
                            json.loads(pretty.stdout)
                    if name == "n10-local":
                        self.assertIn(N10_LINE, pretty.stderr.splitlines())
                        self.assertIn(N10_LINE, default.stderr.splitlines())

    def test_about_default_json_uses_through_the_app_honesty(self) -> None:
        baseline_wheel = QAFIX4_PACK / WHEEL_NAME
        if not baseline_wheel.is_file():
            self.skipTest("qafix4 wheel must be on disk for 5565000 byte compare")
        with tempfile.TemporaryDirectory(prefix="rs-about-ev-") as raw:
            root = Path(raw)
            ws = root / "ws"
            ws.mkdir()
            base_rs = _install_wheel(root / "base", baseline_wheel)
            current_wheel = _wheel_current_tree(root / "cur-wheel")
            cur_rs = _install_wheel(root / "cur", current_wheel)
            left = _run_rs(base_rs, ["about"], ws)
            right = _run_rs(cur_rs, ["about"], ws)
            self.assertEqual(left.returncode, 0)
            self.assertEqual(right.returncode, 0)
            self.assertNotEqual(
                left.stdout,
                right.stdout,
                "about JSON must change from the qafix4 unqualified cannot-approve line",
            )
            payload = json.loads(right.stdout)
            summary = payload["summary"]
            self.assertIn("Plugins/agents cannot approve through the app.", summary)
            self.assertIn(
                "A program running as you that can edit RunSpecimen's files "
                "can still add a fake approval to the record.",
                summary,
            )
            self.assertIn(
                "To protect against that, sign receipts with a key the agent can't access.",
                summary,
            )
            self.assertNotIn("Plugins/agents cannot approve.", summary)
            pretty = _run_rs(cur_rs, ["--pretty", "--color", "never", "about"], ws)
            self.assertEqual(pretty.returncode, right.returncode)
            self.assertIn("cannot approve through the app", pretty.stdout)

    def test_holder_policy_allow_refuse_matrix_matches_qafix4(self) -> None:
        baseline_wheel = QAFIX4_PACK / WHEEL_NAME
        if not baseline_wheel.is_file():
            self.skipTest("qafix4 wheel must be on disk for holder-policy matrix")
        with tempfile.TemporaryDirectory(prefix="rs-holder-mx-") as raw:
            root = Path(raw)
            ws = root / "ws"
            ws.mkdir()
            (ws / "work").mkdir()
            (ws / "outputs").mkdir()
            (ws / "work" / "job.py").write_text("print('ok')\n", encoding="utf-8")
            ordinary = write_contract(ws, "ordinary.json", base_contract())
            policies = {
                "local": write_contract(
                    ws, "local.json", base_contract(execution_approval="local")
                ),
                "companion": write_contract(
                    ws,
                    "companion.json",
                    base_contract(execution_approval="companion"),
                ),
                "dual": write_contract(
                    ws, "dual.json", base_contract(execution_approval="dual")
                ),
            }
            base_rs = _install_wheel(root / "base", baseline_wheel)
            current_wheel = _wheel_current_tree(root / "cur-wheel")
            cur_rs = _install_wheel(root / "cur", current_wheel)

            def first_error(proc: subprocess.CompletedProcess[str]) -> str:
                for line in proc.stderr.splitlines():
                    if line.startswith("RunSpecimen error:"):
                        return line
                return proc.stderr.strip()

            ordinary_base = _run_rs(
                base_rs,
                ["approve", "--workspace", str(ws), "--contract", str(ordinary)],
                ws,
            )
            ordinary_cur = _run_rs(
                cur_rs,
                ["approve", "--workspace", str(ws), "--contract", str(ordinary)],
                ws,
            )
            self.assertNotEqual(ordinary_base.returncode, 0)
            self.assertEqual(ordinary_base.returncode, ordinary_cur.returncode)
            self.assertEqual(first_error(ordinary_base), first_error(ordinary_cur))
            self.assertIn("interactive tty", first_error(ordinary_cur).lower())

            for policy, path in policies.items():
                with self.subTest(policy=policy):
                    left = _run_rs(
                        base_rs,
                        ["approve", "--workspace", str(ws), "--contract", str(path)],
                        ws,
                    )
                    right = _run_rs(
                        cur_rs,
                        ["approve", "--workspace", str(ws), "--contract", str(path)],
                        ws,
                    )
                    self.assertNotEqual(left.returncode, 0, policy)
                    self.assertEqual(left.returncode, right.returncode, policy)
                    self.assertEqual(first_error(left), first_error(right), policy)
                    self.assertEqual(
                        first_error(right),
                        f"RunSpecimen error: execution policy {policy} has no typed-phrase fallback",
                    )


if __name__ == "__main__":
    unittest.main()
