# RunSpecimen for macOS

Native SwiftUI companion for [RunSpecimen](https://github.com/darashkevich/runspecimen) —
a local safety and evidence layer for one human-approved bounded run at a time.

This app is a **thin shell** over the CLI enforcement engine. It does not reimplement
leases, approval binding, or receipt verification in Swift.

## Distribution stance

See **[APP_STORE.md](APP_STORE.md)**, **[NOTARIZATION.md](NOTARIZATION.md)**, and
**[docs/ADR-001-architecture.md](docs/ADR-001-architecture.md)**.

- **v1 ship:** Developer ID + notarization (Target B), sandbox-compatible code paths.
- **Stretch:** Mac App Store (Target A) after review-risk mitigation / optional embedded helper
  ([Helpers/README.md](Helpers/README.md), [ADR-002](docs/ADR-002-embedded-helper.md)).

## What works in this scaffold

| Capability | Status |
| --- | --- |
| Brand-first empty state, flight-ops theme | Done |
| Workspace picker via Open panel + security-scoped bookmarks | Done |
| CLI via Open panel + bookmark restore + PATH/PyPI location probe | Done |
| Minimum CLI gate (`0.2.0rc9+`) with clear error banners | Done |
| `doctor`, `--version`, `status`, `validate` integration | Done |
| Lifecycle status + evidence / receipt inspector (read-only) | Done |
| Action bar gating (approve / run / postflight / verify / dashboard) | Done |
| Dashboard launch with child process tracked + killed on quit | Done |
| Approve sheet with real PTY → `runspecimen approve` + VoiceOver labels | Done |
| Settings (CLI path, version, privacy, non-goals) | Done |
| App Sandbox entitlements + PrivacyInfo | Done |
| Signing / notarization scripts (`Scripts/sign_and_notarize.sh`) | Ready when Developer ID cert present |
| Notarized / MAS archive | Blocked without Developer ID identity + full Xcode |

## Requirements

- macOS 14+
- Xcode 15+ recommended for Archive (Command Line Tools can compile sources via `Scripts/build_app.sh`)
- Installed `runspecimen` CLI **0.2.0rc9+** (PyPI or this repo’s `pip install .`)

```bash
python3 -m pip install 'runspecimen==0.2.0rc9'
# or from this repository:
# sh scripts/bootstrap_dev.sh
runspecimen --version
```

## Build (local smoke)

```bash
cd apps/macos
./Scripts/build_app.sh          # produces build/RunSpecimen.app (ad-hoc signed)
open build/RunSpecimen.app
```

## Sign + notarize (Developer ID)

```bash
./Scripts/check_signing_identity.sh   # fails with setup steps if no cert
# cp Config/signing.env.example Config/signing.env  # then fill secrets locally
./Scripts/sign_and_notarize.sh all    # sign → notarize → staple → zip
```

Full operator checklist: **[NOTARIZATION.md](NOTARIZATION.md)**.

## Approval invariant

Human approval remains interactive. The Approve sheet attaches `runspecimen approve` to a
**real PTY** so the engine’s `isatty` gate still holds. The app never types `APPROVE` for
the user and never offers an agent/plugin approval channel.

## Non-goals (also shown in-app)

Not an OS sandbox, job scheduler, compliance suite, or asymmetric signature system.
Certificates are locally verifiable hash-chained receipts — not digital signatures.
HMAC / hash chains must never be labeled as asymmetric signatures in UI copy.

## License

Apache-2.0 (same as the parent RunSpecimen project).
