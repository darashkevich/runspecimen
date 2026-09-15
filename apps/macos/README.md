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
| CLI via Open panel + bookmark → bundled Helpers → PATH probe | Done |
| Minimum CLI gate (`0.2.0rc9+`) with version-mismatch banners | Done |
| `doctor`, `--version`, `status`, `validate` integration | Done |
| Lifecycle status + evidence / receipt inspector (copy, empty/error) | Done |
| Action bar gating + ⌘1–5 / ⇧⌘A / ⇧⌘D shortcuts (Run/Postflight confirm) | Done |
| Dashboard launch tracked; stop on demand; killed sync on quit | Done |
| Approve sheet with real PTY → `runspecimen approve` + VoiceOver labels | Done |
| Settings (CLI path, version, source, privacy, non-goals) | Done |
| About panel (app/CLI version + privacy link) | Done |
| Menu commands (Workspace, Lifecycle, Engine, Help, About) | Done |
| Helpers staging (`--from-src` package tree) + `Contents/Helpers` in builds | Done for local/Target B |
| Optional PyInstaller freeze (`RS_FREEZE_HELPER=1` / `--frozen-helper`) | Local when PyInstaller installed; CI skips |
| App Sandbox entitlements + PrivacyInfo + helper inherit entitlements | Done |
| `swift test` + `Scripts/smoke_macos.sh` (no GUI, helper e2e) | Done |
| Signing / notarization scripts (`Scripts/sign_and_notarize.sh`) | Ready when Developer ID cert present |
| Notarized / MAS archive | Blocked without Developer ID identity + full Xcode |

## Requirements

- macOS 14+
- Xcode 15+ / Swift 5.9+ (Command Line Tools can build via SwiftPM + `Scripts/build_app.sh`)
- Installed `runspecimen` CLI **0.2.0rc9+** (PyPI or this repo’s `pip install .`), **or** a staged helper under `Helpers/payload/`

```bash
python3 -m pip install 'runspecimen==0.2.0rc9'
# or from this repository:
# sh scripts/bootstrap_dev.sh
runspecimen --version
```

## Build (local smoke)

```bash
cd apps/macos
./Scripts/smoke_macos.sh        # swift test + build + layout checks (+ CLI probe if on PATH)
./Scripts/build_app.sh          # produces build/RunSpecimen.app (ad-hoc signed)
open build/RunSpecimen.app
```

Operator release steps (cert, notarize, freeze): **[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)**.

## Bundled helper (optional)

```bash
./Scripts/stage_helper.sh --from-src --verify   # Apache-2.0 package tree + launcher
./Scripts/build_app.sh                          # copies into Contents/Helpers/
# Or: ./Scripts/build_app.sh --from-src
# In-app: Engine → Prefer Bundled Helper  (Source = “Bundled Helpers”)
```

Dry-run copy of an installed CLI (may embed an absolute shebang):

```bash
./Scripts/stage_helper.sh --from "$(command -v runspecimen)"
./Scripts/build_app.sh
```

`--from-src` needs host Python 3.9+ at runtime. Optional PyInstaller freeze:

```bash
# End-to-end (local; not CI-default)
python3 -m pip install --user 'pyinstaller>=6'
RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh --verify
./Scripts/build_app.sh

# Or one-shot (falls back to --from-src if PyInstaller missing):
./Scripts/build_app.sh --frozen-helper
```

See [Helpers/README.md](Helpers/README.md). `smoke_macos.sh` always re-stages `--from-src`.
## Sign + notarize (Developer ID)

```bash
./Scripts/check_signing_identity.sh   # fails with setup steps if no cert
# cp Config/signing.env.example Config/signing.env  # then fill secrets locally
./Scripts/sign_and_notarize.sh all    # sign → notarize → staple → zip
```

Full operator checklist: **[NOTARIZATION.md](NOTARIZATION.md)** and
**[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)**.
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
