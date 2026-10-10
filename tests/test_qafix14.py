"""qafix14 regressions: static verifier, event create race, no-follow locks."""

from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import SRC, RunSpecimenTestCase
from tests.test_rc15_qafix_docs import (
    VERIFY_INSTALLED,
    _install_and_verify,
    _pin_wheel,
)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.approve import load_approval
from runspecimen.errors import LeaseError, PathEscapeError, SigningError
from runspecimen.events import EventLog
from runspecimen.execution_holder import ExecutionHolder, HolderRefusal
from runspecimen.lease import Lease
from runspecimen.paths import (
    APPROVAL_FILENAME,
    EVENTS_APPEND_LOCK_FILENAME,
    EVENTS_FILENAME,
    LEASE_FILENAME,
    LEASE_META_FILENAME,
    STATE_FILENAME,
)
from runspecimen.pubkey import hold_keys_dir_lock
from runspecimen.state import load_state


def _first_append(state_dir: str, ready, go, queue) -> None:
    src = str(Path(__file__).resolve().parents[1] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from pathlib import Path as P

    from runspecimen.events import EventLog as Log

    log = Log.for_state_dir(P(state_dir))
    ready.set()
    go.wait(timeout=30)
    record = log.append("first", {"who": multiprocessing.current_process().name})
    queue.put(record.seq)


class Qafix14EventAndLockTests(RunSpecimenTestCase):
    def test_latest03_concurrent_first_append_assigns_seq_1_and_2(self) -> None:
        state_dir = self.ws / ".runspecimen" / "runs" / "camp" / "first-append"
        state_dir.mkdir(parents=True)
        # The log file must not exist yet. Both appenders create it.
        self.assertFalse((state_dir / EVENTS_FILENAME).exists())
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        go = ctx.Event()
        procs = []
        readies = []
        for _name in ("a", "b"):
            ready = ctx.Event()
            proc = ctx.Process(target=_first_append, args=(str(state_dir), ready, go, queue))
            procs.append(proc)
            readies.append(ready)
            proc.start()
        for ready in readies:
            self.assertTrue(ready.wait(timeout=10))
        go.set()
        seqs = sorted(queue.get(timeout=30) for _ in procs)
        for proc in procs:
            proc.join(timeout=10)
            self.assertEqual(proc.exitcode, 0)
        self.assertEqual(seqs, [1, 2])
        log = EventLog.for_state_dir(state_dir)
        ok, message = log.verify_chain()
        self.assertTrue(ok, message)
        self.assertEqual([record.seq for record in log.read_all()], [1, 2])

    def test_latest04_event_append_lock_symlink_is_refused(self) -> None:
        state_dir = self.ws / ".runspecimen" / "runs" / "camp" / "lock-symlink"
        state_dir.mkdir(parents=True)
        target = state_dir / "secret"
        target.write_text("keep", encoding="utf-8")
        lock = state_dir / EVENTS_APPEND_LOCK_FILENAME
        lock.symlink_to(target)
        log = EventLog.for_state_dir(state_dir)
        with self.assertRaises(PathEscapeError) as caught:
            log.append("x", {"n": 1})
        self.assertIn("symlink", str(caught.exception).lower())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        self.assertTrue(lock.is_symlink())

    def test_latest04_lease_lock_symlink_is_refused(self) -> None:
        lock_dir = self.ws / ".runspecimen"
        lock_dir.mkdir(parents=True)
        target = self.ws / "lease-secret"
        target.write_text("keep", encoding="utf-8")
        lock = lock_dir / LEASE_FILENAME
        lock.symlink_to(target)
        lease = Lease(lock_dir, holder="qafix14")
        with self.assertRaises(LeaseError) as caught:
            lease.acquire()
        self.assertIn("symlink", str(caught.exception).lower())
        with self.assertRaises(LeaseError):
            lease.is_locked_by_other()
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        self.assertTrue(lock.is_symlink())

    def test_latest04_lease_meta_symlink_is_refused(self) -> None:
        lock_dir = self.ws / ".runspecimen"
        lock_dir.mkdir(parents=True)
        target = lock_dir / "meta-real.json"
        target.write_text('{"pid": 1, "created_ts": 1, "holder": "x"}\n', encoding="utf-8")
        meta = lock_dir / LEASE_META_FILENAME
        meta.symlink_to(target.name)
        lease = Lease(lock_dir, holder="qafix14")
        with self.assertRaises(PathEscapeError) as caught:
            lease.read_meta()
        self.assertIn("symlink", str(caught.exception).lower())

    def test_latest04_keys_lock_symlink_is_refused(self) -> None:
        target = self.ws / "keys-secret"
        target.write_text("keep", encoding="utf-8")
        control = self.ws / ".runspecimen"
        control.mkdir()
        lock = control / "keys.op.lock"
        lock.symlink_to(target)
        with self.assertRaises(SigningError) as caught:
            with hold_keys_dir_lock(self.ws):
                pass
        self.assertIn("symlink", str(caught.exception).lower())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        self.assertTrue(lock.is_symlink())

    def test_latest04_holder_op_lock_symlink_is_refused(self) -> None:
        root = self.ws / "holder-root"
        holder = ExecutionHolder(root, allow_test_double=True)
        target = self.ws / "holder-secret"
        target.write_text("keep", encoding="utf-8")
        lock = root / ".holder.op.lock"
        lock.symlink_to(target)
        with self.assertRaises(HolderRefusal) as caught:
            with holder._transaction():
                pass
        self.assertIn("symlink", str(caught.exception).lower())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")
        self.assertTrue(lock.is_symlink())

    def test_latest04_state_and_approval_symlinks_are_refused(self) -> None:
        state_dir = self.ws / ".runspecimen" / "runs" / "camp" / "state-links"
        state_dir.mkdir(parents=True)
        real_state = state_dir / "real-state.json"
        real_state.write_text('{"phase": "none"}\n', encoding="utf-8")
        state = state_dir / STATE_FILENAME
        state.symlink_to(real_state.name)
        with self.assertRaises(PathEscapeError) as state_caught:
            load_state(state_dir)
        self.assertIn("symlink", str(state_caught.exception).lower())
        real_approval = state_dir / "real-approval.json"
        real_approval.write_text("{}\n", encoding="utf-8")
        approval = state_dir / APPROVAL_FILENAME
        approval.symlink_to(real_approval.name)
        with self.assertRaises(PathEscapeError) as approval_caught:
            load_approval(state_dir)
        self.assertIn("symlink", str(approval_caught.exception).lower())
        self.assertEqual(real_state.read_text(encoding="utf-8"), '{"phase": "none"}\n')
        self.assertEqual(real_approval.read_text(encoding="utf-8"), "{}\n")


class Qafix14VerifierStaticPhaseTests(unittest.TestCase):
    def _require_pin(self) -> Path:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        return pin

    def _refuse_without_marker(self, plant, *, needles: tuple[str, ...]) -> None:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            plant(hook, marker)

        def inspect(result: object) -> None:
            completed = result
            output = completed.stdout + completed.stderr  # type: ignore[attr-defined]
            self.assertNotEqual(completed.returncode, 0, output)  # type: ignore[attr-defined]
            self.assertFalse(box["marker"].exists(), output)
            payload = json.loads(completed.stdout.split("---")[0])  # type: ignore[attr-defined]
            self.assertFalse(payload["ok"], payload)
            blob = json.dumps(payload)
            for needle in needles:
                self.assertIn(needle, blob, payload)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)

    def test_latest01_sitecustomize_package_is_refused_with_no_side_effect(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            package = Path(hook.site) / "sitecustomize"  # type: ignore[attr-defined]
            package.mkdir()
            (package / "__init__.py").write_text(
                f"open({str(marker)!r}, 'w').write('ran')\n",
                encoding="utf-8",
            )

        self._refuse_without_marker(plant, needles=("sitecustomize",))

    def test_latest01_usercustomize_package_is_refused_with_no_side_effect(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            package = Path(hook.site) / "usercustomize"  # type: ignore[attr-defined]
            package.mkdir()
            (package / "__init__.py").write_text(
                f"open({str(marker)!r}, 'w').write('ran')\n",
                encoding="utf-8",
            )

        self._refuse_without_marker(plant, needles=("usercustomize",))

    def test_sib02_site_packages_pth_is_refused_with_no_side_effect(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            path = Path(hook.site) / "zz-side-effect.pth"  # type: ignore[attr-defined]
            path.write_text(
                f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')\n",
                encoding="utf-8",
            )

        self._refuse_without_marker(plant, needles=("zz-side-effect.pth",))

    def test_sib01_debian_dist_packages_pth_and_module_have_no_side_effect(self) -> None:
        pyver = f"python{sys.version_info[0]}.{sys.version_info[1]}"
        relatives = (
            Path("lib") / pyver / "dist-packages",
            Path("lib") / "python3" / "dist-packages",
            Path("local") / "lib" / pyver / "dist-packages",
        )

        def plant(hook: object, marker: Path) -> None:
            venv_dir = Path(hook.venv_dir)  # type: ignore[attr-defined]
            for relative in relatives:
                directory = venv_dir / relative
                directory.mkdir(parents=True)
                (directory / "zz-debian.pth").write_text(
                    f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')\n",
                    encoding="utf-8",
                )
                (directory / "evilmod.py").write_text(
                    f"open({str(marker)!r}, 'w').write('mod')\n",
                    encoding="utf-8",
                )

        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            plant(hook, marker)

        def inspect(result: object) -> None:
            output = result.stdout + result.stderr  # type: ignore[attr-defined]
            self.assertNotEqual(result.returncode, 0, output)  # type: ignore[attr-defined]
            self.assertFalse(box["marker"].exists(), output)
            payload = json.loads(result.stdout.split("---")[0])  # type: ignore[attr-defined]
            blob = json.dumps(payload)
            for relative in relatives:
                self.assertIn(str(relative).replace("\\", "/"), blob.replace("\\", "/"), payload)
            self.assertIn("evilmod.py", blob)
            self.assertIn("zz-debian.pth", blob)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)

    def test_sib01_dist_packages_module_alone_is_refused_with_no_side_effect(self) -> None:
        pyver = f"python{sys.version_info[0]}.{sys.version_info[1]}"

        def plant(hook: object, marker: Path) -> None:
            directory = Path(hook.venv_dir) / "lib" / pyver / "dist-packages"  # type: ignore[attr-defined]
            directory.mkdir(parents=True)
            (directory / "json.py").write_text(
                f"open({str(marker)!r}, 'w').write('shadow')\n",
                encoding="utf-8",
            )

        self._refuse_without_marker(plant, needles=("dist-packages", "json.py"))

    def test_latest02_tampered_launcher_is_not_executed(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            launcher = Path(hook.launcher)  # type: ignore[attr-defined]
            data = launcher.read_bytes()
            newline = data.find(b"\n")
            injected = f"open({str(marker)!r}, 'w').write('ran')\n".encode()
            launcher.write_bytes(data[: newline + 1] + injected + data[newline + 1 :])

        self._refuse_without_marker(plant, needles=("pinned pip template",))


if __name__ == "__main__":
    unittest.main()
