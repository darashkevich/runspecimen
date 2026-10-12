"""qafix30: pip-free install, and rejected environments must not run a canary."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_pinned_wheel.py"
VERIFIER = ROOT / "scripts" / "verify_installed_wheel.py"
HUMAN = ROOT / "docs" / "HUMAN-ACCEPTANCE.md"


def _load(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wheel(path: Path, members: dict[str, bytes], *, version: str = "0.2.0rc15") -> None:
    dist = f"runspecimen-{version}.dist-info"
    payload = dict(members)
    payload.setdefault(
        f"{dist}/entry_points.txt",
        b"[console_scripts]\nrunspecimen = runspecimen.cli:main\n",
    )
    payload.setdefault(f"{dist}/METADATA", b"Name: runspecimen\n")
    payload.setdefault(f"{dist}/WHEEL", b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    payload.setdefault(f"{dist}/RECORD", b"")
    payload.setdefault("runspecimen/__init__.py", b"__version__ = '0.2.0rc15'\n")
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in payload.items():
            archive.writestr(name, data)


def _venv(path: Path) -> None:
    subprocess.run(
        [sys.executable, "-I", "-S", "-m", "venv", "--without-pip", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


class InstallerRefusalTests(unittest.TestCase):
    def test_hash_mismatch_writes_nothing_and_does_not_run_canary(self) -> None:
        module = _load(INSTALLER, "install_pinned_wheel_hash")
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-hash-") as raw:
            root = Path(raw)
            marker = root / "canary"
            wheel = root / "runspecimen-0.2.0rc15-py3-none-any.whl"
            _wheel(
                wheel,
                {
                    "runspecimen/__init__.py": (
                        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
                    ).encode()
                },
            )
            venv = root / "venv"
            _venv(venv)
            with self.assertRaises(module.InstallRefusal):
                module.install_pinned_wheel(wheel, venv, "0" * 64)
            self.assertFalse(marker.exists())
            self.assertFalse((venv / "bin" / "runspecimen").exists())
            self.assertFalse(list((venv / "lib").rglob("runspecimen/__init__.py")))

    def test_isolated_flags_are_required(self) -> None:
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--wheel", "x", "--venv", "y", "--expected-sha256", "ab"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("-I -S", result.stderr + result.stdout)

    def test_traversal_duplicate_link_and_overwrite_are_refused(self) -> None:
        module = _load(INSTALLER, "install_pinned_wheel_layout")
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-layout-") as raw:
            root = Path(raw)
            venv = root / "venv"
            _venv(venv)
            outside = root / "outside.txt"

            traversal = root / "runspecimen-0.2.0rc15-py3-none-any.whl"
            _wheel(traversal, {})
            with zipfile.ZipFile(traversal, "a") as archive:
                archive.writestr("../outside.txt", b"escaped")
            digest = hashlib.sha256(traversal.read_bytes()).hexdigest()
            with self.assertRaises(module.InstallRefusal):
                module.install_pinned_wheel(traversal, venv, digest)
            self.assertFalse(outside.exists())

            duplicate = root / "dup-runspecimen-0.2.0rc15-py3-none-any.whl"
            # The helper name must still match the wheel version parser.
            duplicate = root / "runspecimen-0.2.0rc15-py3-none-any.whl"
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("runspecimen/__init__.py", b"a = 1\n")
                archive.writestr("runspecimen/__init__.py", b"a = 2\n")
                archive.writestr(
                    "runspecimen-0.2.0rc15.dist-info/entry_points.txt",
                    b"[console_scripts]\nrunspecimen = runspecimen.cli:main\n",
                )
            duplicate.write_bytes(buffer.getvalue())
            with self.assertRaises(module.InstallRefusal):
                module.install_pinned_wheel(
                    duplicate, venv, hashlib.sha256(duplicate.read_bytes()).hexdigest()
                )

            linked = root / "link-runspecimen-0.2.0rc15-py3-none-any.whl"
            linked = root / "runspecimen-0.2.0rc15-py3-none-any.whl"
            info = zipfile.ZipInfo("runspecimen/link.py")
            info.external_attr = (0o120777) << 16
            info.create_system = 3
            with zipfile.ZipFile(linked, "w") as archive:
                archive.writestr("runspecimen/__init__.py", b"a = 1\n")
                archive.writestr(
                    "runspecimen-0.2.0rc15.dist-info/entry_points.txt",
                    b"[console_scripts]\nrunspecimen = runspecimen.cli:main\n",
                )
                archive.writestr(info, b"target")
            with self.assertRaises(module.InstallRefusal):
                module.install_pinned_wheel(
                    linked, venv, hashlib.sha256(linked.read_bytes()).hexdigest()
                )

            good = root / "runspecimen-0.2.0rc15-py3-none-any.whl"
            _wheel(good, {"runspecimen/__init__.py": b"VALUE = 1\n"})
            purelib = module.venv_purelib(venv)
            planted = purelib / "runspecimen"
            planted.mkdir()
            (planted / "__init__.py").write_text("VALUE = 'kept'\n", encoding="utf-8")
            with self.assertRaises(module.InstallRefusal):
                module.install_pinned_wheel(
                    good, venv, hashlib.sha256(good.read_bytes()).hexdigest()
                )
            self.assertEqual((planted / "__init__.py").read_text(encoding="utf-8"), "VALUE = 'kept'\n")

    def test_symlink_ancestor_is_refused(self) -> None:
        module = _load(INSTALLER, "install_pinned_wheel_symlink")
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-ancestor-") as raw:
            root = Path(raw)
            venv = root / "venv"
            _venv(venv)
            lib = venv / "lib"
            moved = root / "moved-lib"
            lib.rename(moved)
            lib.symlink_to(moved)
            wheel = root / "runspecimen-0.2.0rc15-py3-none-any.whl"
            _wheel(wheel, {})
            with self.assertRaises(module.InstallRefusal) as ctx:
                module.install_pinned_wheel(
                    wheel, venv, hashlib.sha256(wheel.read_bytes()).hexdigest()
                )
            self.assertIn("symlink", str(ctx.exception).lower())

    def test_clean_install_matches_template_and_does_not_import(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-clean-") as raw:
            root = Path(raw)
            marker = root / "canary"
            wheel = root / "runspecimen-0.2.0rc15-py3-none-any.whl"
            _wheel(
                wheel,
                {
                    "runspecimen/__init__.py": (
                        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
                    ).encode()
                },
            )
            venv = root / "venv"
            _venv(venv)
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(INSTALLER),
                    "--wheel",
                    str(wheel),
                    "--venv",
                    str(venv),
                    "--expected-sha256",
                    digest,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())
            launcher = venv / "bin" / "runspecimen"
            body = launcher.read_bytes().split(b"\n", 1)[1]
            module = _load(VERIFIER, "verify_for_template")
            self.assertIn(body, module.KNOWN_CONSOLE_SCRIPT_BODIES)
            self.assertFalse((venv / "bin" / "pip").exists())


class CanaryRefusalTests(unittest.TestCase):
    def test_shebang_argument_is_refused_without_running_canary(self) -> None:
        module = _load(VERIFIER, "verify_qa2201")
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-shebang-") as raw:
            root = Path(raw)
            marker = root / "canary"
            bindir = root / "bin"
            bindir.mkdir()
            python = bindir / "python"
            python.symlink_to(Path(os.path.realpath(sys.executable)))
            launcher = bindir / "runspecimen"
            launcher.write_bytes(
                f"#!{python} -c 'open({str(marker)!r},\"w\").write(\"ran\")'\n".encode()
                + module.PIP_DISTLIB_CONSOLE_SCRIPT_BODY
            )
            launcher.chmod(0o755)
            with self.assertRaises(module.UnsupportedShebangError):
                module.interpreter_from_launcher(launcher)
            self.assertFalse(marker.exists())

    def test_untrusted_interpreter_name_is_not_executed(self) -> None:
        module = _load(VERIFIER, "verify_qa2202")
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-python2-") as raw:
            root = Path(raw)
            marker = root / "canary"
            bindir = root / "bin"
            bindir.mkdir()
            canary = bindir / "python2"
            canary.write_text(
                f"#!/bin/sh\n: > {marker}\n",
                encoding="utf-8",
            )
            canary.chmod(canary.stat().st_mode | stat.S_IXUSR)
            launcher = bindir / "runspecimen"
            launcher.write_bytes(f"#!{canary}\n".encode() + module.PIP_DISTLIB_CONSOLE_SCRIPT_BODY)
            launcher.chmod(0o755)
            with self.assertRaises(module.UnsupportedShebangError):
                module.interpreter_from_launcher(launcher)
            findings = module.scan_venv_bin(bindir)
            self.assertTrue(any("python2" in item for item in findings), findings)
            self.assertFalse(marker.exists())

    def test_changed_launcher_body_is_not_executed(self) -> None:
        module = _load(VERIFIER, "verify_changed_body")
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-body-") as raw:
            root = Path(raw)
            marker = root / "canary"
            bindir = root / "bin"
            bindir.mkdir()
            python = bindir / "python"
            python.symlink_to(Path(os.path.realpath(sys.executable)))
            launcher = bindir / "runspecimen"
            original = f"#!{python}\n".encode() + module.PIP_DISTLIB_CONSOLE_SCRIPT_BODY
            launcher.write_bytes(original)
            expected = module.launcher_body_after_shebang(original)
            launcher.write_bytes(
                f"#!{python}\n".encode()
                + f"open({str(marker)!r},'w').write('ran')\n".encode()
            )
            with self.assertRaises(RuntimeError) as ctx:
                module.probe_launcher_doctor(
                    launcher,
                    {},
                    base=Path(sys.executable),
                    extra_paths=[],
                    expected_body=expected,
                )
            self.assertIn("not started", str(ctx.exception))
            self.assertFalse(marker.exists())

    def test_private_copy_does_not_import_a_replaced_live_module(self) -> None:
        module = _load(VERIFIER, "verify_private_copy")
        with tempfile.TemporaryDirectory(prefix="rs-qafix30-copy-") as raw:
            root = Path(raw)
            marker = root / "canary"
            site = root / "site"
            package = site / "runspecimen"
            package.mkdir(parents=True)
            original = b"VALUE = 'checked'\n"
            (package / "__init__.py").write_bytes(original)
            captured, error = module.capture_member_bytes(site, ["runspecimen/__init__.py"])
            self.assertIsNone(error)
            assert captured is not None
            (package / "__init__.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
                encoding="utf-8",
            )
            changed = module.changed_member(site, captured)
            self.assertIsNotNone(changed)
            private = module.write_private_site(root / "private", captured)
            self.assertEqual((private / "runspecimen" / "__init__.py").read_bytes(), original)
            self.assertFalse(marker.exists())


class SheetShellTests(unittest.TestCase):
    def test_missing_wheel_and_existing_venv_do_not_print_false_success(self) -> None:
        text = HUMAN.read_text(encoding="utf-8")
        import re
        fences = "\n".join(re.findall(r"```(?:bash|sh)?\n(.*?)```", text, flags=re.S))
        self.assertNotIn("|| true", fences)
        self.assertNotIn("setuptools*", fences)
        blocks = []
        for block in text.split("```"):
            if "rs_ok N1-wheel" in block or "export PACK" in block or 'test ! -e "$VENV"' in block or "basepy -m venv" in block:
                blocks.append(block)
        self.assertGreaterEqual(len(blocks), 3)
        for shell in ("bash", "zsh"):
            if shell == "zsh" and not _which("zsh"):
                self.fail("zsh is required; a skip is not a pass")
            with tempfile.TemporaryDirectory(prefix=f"rs-qafix30-{shell}-") as raw:
                root = Path(raw)
                pack = root / "pack"
                pack.mkdir()
                script = textwrap.dedent(
                    f"""
                    set +e
                    export PACK={str(pack)!r}
                    export WHEEL="$PACK/missing.whl"
                    export WORK={str(root / "work")!r}
                    mkdir -p "$WORK"
                    export VENV="$WORK/venv"
                    export RS="$VENV/bin/runspecimen"
                    export PY="$VENV/bin/python"
                    export BASE_PY={sys.executable!r}
                    rs_ok() {{ echo "STEP $1 exit=$2"; if [ "$2" -ne 0 ]; then echo "FAIL: step $1"; exit 1; fi; }}
                    test -f "$WHEEL"
                    rs_ok N1-wheel $?
                    test ! -e "$VENV"
                    rs_ok N1-venv-absent $?
                    echo SHOULD_NOT_REACH
                    """
                )
                result = subprocess.run(
                    [shell, "-o", "nomatch", "-c", script] if shell == "zsh" else [shell, "-c", script],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("FAIL: step N1-wheel", output)
                self.assertNotIn("STEP N1-venv-absent exit=0", output)
                self.assertNotIn("SHOULD_NOT_REACH", output)

            with tempfile.TemporaryDirectory(prefix=f"rs-qafix30-exist-{shell}-") as raw:
                root = Path(raw)
                work = root / "work"
                work.mkdir()
                (work / "venv").mkdir()
                script = textwrap.dedent(
                    f"""
                    export VENV={str(work / "venv")!r}
                    rs_ok() {{ echo "STEP $1 exit=$2"; if [ "$2" -ne 0 ]; then echo "FAIL: step $1"; exit 1; fi; }}
                    test ! -e "$VENV"
                    rs_ok N1-venv-absent $?
                    echo SHOULD_NOT_CREATE
                    """
                )
                result = subprocess.run(
                    [shell, "-c", script],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("FAIL: step N1-venv-absent", output)
                self.assertNotIn("SHOULD_NOT_CREATE", output)


def _which(name: str) -> bool:
    from shutil import which

    return which(name) is not None


if __name__ == "__main__":
    unittest.main()
