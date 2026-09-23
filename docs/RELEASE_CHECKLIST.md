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
- [x] All symlinked control-plane directories rejected (save, load, list-keys).
- [x] sign and verify-signature CLI commands import and execute correctly.
- [x] Full release gate passes on every supported Python version in CI
  (matrix: Linux 3.9-3.14, macOS 3.11/3.14).
- [x] Wheel is built and smoke-tested from a clean target directory.
- [x] Release smoke includes keygen/list-keys success and sign/verify-signature error handling.
- [x] Plugin and skill validators pass.
- [x] Tag `v0.2.0-rc.14` after the release gate passes on the **merged green**
  commit **and Yahor publishes that GitHub Release** (do not publish or move
  draft `v0.2.0-rc.11`; do not move `v0.2.0-rc.12`).
  Publishing the GitHub Release also uploads `0.2.0rc14` to PyPI via OIDC
  (identical bytes; checksum-only, not attested).
  - Prospective release URL: https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.14

Run `python3 scripts/release_check.py` before tagging. A release candidate is not
a stable release and does not change the explicit limitations in the threat model.


## Stable 0.2.0 gate

**Status: not met.** Published package remains **`0.2.0rc14`**. Do not retag,
promote, or claim rc13 as stable. A release candidate is not a stable release.

### Honesty constraints (must stay true on the cut commit)

- [ ] Default `isolation.backend` remains **`none`** (unconfined). Docs must not
      imply confinement by default.
- [ ] Opt-in `sandbox-exec` / `bwrap` are **not** an OS sandbox; threat model and
      README Limitations language must match receipts (`residual` / claim text).
- [ ] No telemetry / phone-home; TTY `APPROVE` remains the only approval path
      (plugins cannot manufacture approval).

### Already landed (do not re-litigate)

- [x] Linux `bwrap` confinement regression (#19) and follow-on real-spawn coverage
      when CI installs bubblewrap.
- [x] Reproducible wheel/sdist bytes across release builds (#20).
- [x] Publish path downloads GitHub Release assets for PyPI (identical bytes;
      checksum-only until SLSA is intentionally designed).

### Still required before tagging `v0.2.0`

- [ ] Version / classifier bump from `0.2.0rc14` → `0.2.0` (package, plugins,
      docs identity pins) on a dedicated PR.
- [ ] CI green on the exact cut commit (Linux 3.9–3.14, macOS 3.11/3.14, macos-app).
- [ ] Copy audit: USER_GUIDE, THREAT_MODEL, FAQ, SUBMISSION, site pins — no
      “unreleased” language for shipped isolation; no overclaim of sandboxing.
- [ ] `python3 scripts/release_check.py` passes on the cut commit.

### Publish order (only after the gate above is honestly checked)

1. Merge the version bump PR with green CI.
2. Tag `v0.2.0` and publish the GitHub Release (do not move `v0.2.0-rc.*` tags).
3. PyPI via existing OIDC workflow (identical Release bytes).
4. Homebrew tap formula bump for the new sdist.
5. Update site / RELEASE_IDENTITY pins.

**Out of scope for the stable engine cut:** ASC / Mac App Store / TestFlight /
marketplace acceptance.
