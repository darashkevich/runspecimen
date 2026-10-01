"""Combined runtime-trust regressions. These do not repair a live install.

Ownership, mode, and symlink checks run against a private tree. They do not
touch /Applications/RunSpecimen Holder.app and do not prove installed protection.
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from runspecimen.holder_runtime import (
    RuntimeTrustError,
    assert_path_chain,
    assert_shipped_runtime_chain,
    refuse_user_python_injection,
)


class RuntimeTrustChainTests(unittest.TestCase):
    def _tree(self, root: Path) -> None:
        pkg = root / "runspecimen"
        pkg.mkdir(parents=True)
        for name in (
            "__init__.py",
            "holder_daemon.py",
            "holder_entry.py",
            "holder_drop_exec.py",
            "holder_runtime.py",
            "holder_io.py",
            "holder_adapter.py",
            "execution_holder.py",
            "holder_asymmetric.py",
            "holder_protocol.py",
        ):
            (pkg / name).write_text("# fixture\n", encoding="utf-8")
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)

    def test_symlink_mode_and_injection_fail_closed_together(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-trust-") as td:
            root = Path(td).resolve() / "Resources"
            self._tree(root)
            uid = os.getuid()
            assert_path_chain(root / "runspecimen" / "holder_entry.py", require_uid=uid)
            refuse_user_python_injection({})
            link_parent = Path(td).resolve() / "linked"
            link_parent.mkdir()
            link = link_parent / "holder_entry.py"
            link.symlink_to(root / "runspecimen" / "holder_entry.py")
            with self.assertRaises(RuntimeTrustError) as sym:
                assert_path_chain(link, require_uid=uid)
            self.assertIn("symlink", str(sym.exception))
            writable = root / "runspecimen" / "holder_daemon.py"
            writable.chmod(0o666)
            saved = os.environ.get("PYTHONPATH")
            os.environ.pop("PYTHONPATH", None)
            try:
                with self.assertRaises(RuntimeTrustError) as mode:
                    assert_shipped_runtime_chain(root, require_uid=uid)
            finally:
                if saved is None:
                    os.environ.pop("PYTHONPATH", None)
                else:
                    os.environ["PYTHONPATH"] = saved
            self.assertIn("world-writable", str(mode.exception))
            writable.chmod(0o644)
            with self.assertRaises(RuntimeTrustError) as injected:
                refuse_user_python_injection({"PYTHONPATH": "/tmp/not-protected"})
            self.assertIn("PYTHONPATH", str(injected.exception))

    def test_group_writable_component_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rs-trust-") as td:
            root = Path(td).resolve() / "mod"
            root.mkdir()
            target = root / "holder_entry.py"
            target.write_text("x\n", encoding="utf-8")
            target.chmod(0o620)
            with self.assertRaises(RuntimeTrustError) as ctx:
                assert_path_chain(target, require_uid=os.getuid())
            self.assertIn("group-writable", str(ctx.exception))
            self.assertFalse(stat.S_ISLNK(target.lstat().st_mode))
