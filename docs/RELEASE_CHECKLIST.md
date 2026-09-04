# Release candidate checklist

- [x] One non-blocking workspace lease covers each lifecycle mutation.
- [x] Approval requires a real stdin and stdout TTY.
- [x] Contract, source, executable, identity, and expiry are rechecked at launch.
- [x] Asserted outputs are never overwritten.
- [x] Timeout kills the launched process group and cannot be certified.
- [x] Postflight and live receipt verification are mandatory for successors.
- [x] Lease status cannot display a stale holder as active.
- [x] Python package metadata, license, changelog, security policy, and threat model exist.
- [x] Codex and Cursor adapters preserve the CLI enforcement boundary.
- [ ] Full release gate passes on every supported Python version in CI
  (matrix today: 3.9/3.11/3.12 on ubuntu+macos; not every `>=3.9` interpreter).
- [x] Wheel is built and smoke-tested from a clean target directory.
- [x] Plugin and skill validators pass.
- [x] Tag `v0.2.0-rc.3` exists at `d177eff` (annotated tag tip). Post-tag doc/QA
  nits may land on `main` after this commit without moving the tag.

Run `python3 scripts/release_check.py` before tagging. A release candidate is not
a stable release and does not change the explicit limitations in the threat model.
