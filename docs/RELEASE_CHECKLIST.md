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
- [x] Abandoned runs are permanently terminal and cannot be reused.
- [x] Recovery status checks active leases before allowing abandonment.
- [x] Key storage is hardened against symlink escapes and race conditions.
- [x] Receipt authentication requires full evidence verification before signing.
- [x] Configured interpreters are the exact launch vector (fail closed).
- [x] Environment secrets are never persisted (only domain-separated hashes).
- [x] Candidate-receipt substitution attack prevented (certificate must match canonical).
- [x] No validate=False bypass in receipt signing APIs.
- [x] ldd never invoked on untrusted workspace/configured binaries.
- [x] All symlinked control-plane directories rejected (inside and outside workspace).
- [ ] Full release gate passes on every supported Python version in CI
  (matrix: Linux 3.9-3.14, macOS 3.11/3.14).
- [x] Wheel is built and smoke-tested from a clean target directory.
- [x] Plugin and skill validators pass.
- [ ] Tag `v0.2.0-rc.9` after the release gate passes on the release commit.

Run `python3 scripts/release_check.py` before tagging. A release candidate is not
a stable release and does not change the explicit limitations in the threat model.
