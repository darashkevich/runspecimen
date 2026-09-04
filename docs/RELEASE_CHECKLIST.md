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
- [ ] Full release gate passes on every supported Python version in CI.
- [x] Wheel is built and smoke-tested from a clean target directory.
- [x] Plugin and skill validators pass.
- [ ] Tag `v0.2.0-rc.3` only after the above evidence is recorded.

Run `python3 scripts/release_check.py` before tagging. A release candidate is not
a stable release and does not change the explicit limitations in the threat model.
