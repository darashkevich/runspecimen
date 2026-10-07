# Live protected-runtime repair — authorization request (not performed)

Status: **request only**. This pass implemented the isolated runtime/code loading
chain in source (`holder_runtime.py`, HolderDaemon `main.swift`,
`holder_daemon.py`). It did **not** modify, replace, codesign, uninstall,
disable, restart, signal, or reinstall `/Applications/RunSpecimen.app` or
`/Applications/RunSpecimen Holder.app`, and did not touch the live root daemon
or `/Library/Application Support/com.darashkevich.runspecimen.holder`.

Installed P1 remains: the live user-writable Python / root-launcher path under
the installed Holder.

## What Yahor would approve later (exact steps)

1. **Stop the running daemon (Yahor-authorized only)**
   - `launchctl bootout system/com.darashkevich.runspecimen.holder` (or the
     registered BTM/SMAppService daemon label in use), then confirm
     `launchctl print system/…` shows not running and the AF_UNIX socket under
     `/Library/Application Support/com.darashkevich.runspecimen.holder` is gone
     or not serving.
   - Do not signal arbitrary PIDs without confirming they are the holder daemon.

2. **Files replaced (root-owned, non-writable by console user)**
   - Replace `/Applications/RunSpecimen Holder.app` with a build whose
     `Contents/MacOS/RunSpecimenHolderDaemon` matches the protected-runtime
     `main.swift` (no `RS_HOLDER_PYTHON`, no Homebrew, no `PYTHONPATH`).
   - Install an embedded interpreter at
     `…/Contents/Resources/Runtime/bin/python3` **or** pin `/usr/bin/python3`
     only after verifying that module root is root-owned.
   - Install module tree at `…/Contents/Resources/Python/runspecimen/` from the
     release sdist/wheel corresponding to the approved tip SHA (not from a
     user checkout under `/Users`).
   - Preserve `/Library/Application Support/com.darashkevich.runspecimen.holder/state`
     unless Yahor also authorizes a state wipe; do **not** copy user-writable
     modules into that support directory.

3. **Ownership and mode after repair**
   - Entire `RunSpecimen Holder.app` tree: owner `root:wheel`, directories
     `0755` or tighter, files not group/world-writable; no symlinks in the
     interpreter or `runspecimen` module path.
   - Embedded `Runtime/bin/python3` and `Resources/Python`: `root:wheel`, not
     writable by the console user (`uid != 0`).
   - Bootstrap secret file remains `0600` root-owned under support.

4. **Who owns the new interpreter and modules**
   - Interpreter: Apple `/usr/bin/python3` **or** the embedded runtime shipped
     inside Holder.app Resources — never Homebrew, never
     `~/…`, never `RS_HOLDER_PYTHON`.
   - Modules: only the root-owned tree inside Holder.app Resources (or another
     Yahor-approved root-owned prefix outside `/Users`).

5. **Proof the console user cannot write them**
   - As the console user: `test ! -w` on interpreter, `holder_daemon.py`, and
     each path component; `python3 -c` attempting to open those paths for write
     must fail with EACCES.
   - `ls -laO` / `stat` showing `uid=0`, no `uchg` bypass needed; no ACLs
     granting the console user write (`ls -le`).
   - Symlink check: `test ! -L` on each path component of interpreter and
     module root.

6. **Restart only after proof**
   - Re-register/bootstrap the daemon from the new app, confirm socket serves
     the new build identity, then run Yahor-authorized privileged acceptance
     separately. Green unprivileged CI is not that acceptance.

## Explicit non-goals of this request
- No change to `/Applications/RunSpecimen.app` GUI unless separately approved.
- No notarization, ASC submit, merge, or production sign-off in the same step.
