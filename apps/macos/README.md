# RunSpecimen for macOS

Native SwiftUI companion for [RunSpecimen](https://github.com/darashkevich/runspecimen) —
a local safety and evidence layer for one human-approved bounded run at a time.

This app is a **thin shell** over the CLI enforcement engine. It does not reimplement
leases, approval binding, or receipt verification in Swift.

## Distribution stance

**Primary: Mac App Store** — see **[APP_STORE.md](APP_STORE.md)** and
**[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)**.

- Store packaging: `./Scripts/build_app.sh --mas` (frozen Mach-O helper, fail closed).
- Security boundary (sandbox vs payload): **[docs/SECURITY_BOUNDARY.md](docs/SECURITY_BOUNDARY.md)**.
- Secondary: Developer ID notarization — **[NOTARIZATION.md](NOTARIZATION.md)**.
- Architecture: **[docs/ADR-001-architecture.md](docs/ADR-001-architecture.md)**,
  **[docs/ADR-002-embedded-helper.md](docs/ADR-002-embedded-helper.md)**.

## What works

| Capability | Status |
| --- | --- |
| Brand-first empty state, flight-ops theme | Done |
| App icon (`AppIcon.icns` / iconset / 1024) | Done |
| Workspace Open panel + security-scoped bookmarks | Done |
| CLI discovery: bookmark → Helpers → PATH (PATH off on MAS) | Done |
| Minimum CLI gate (`0.2.0rc9+`) | Done |
| `doctor` / `--version` / `status` / `validate` | Done |
| Lifecycle + evidence inspector | Done |
| Approve sheet with real PTY (never auto-`APPROVE`) | Done |
| Dashboard tracked + killed on quit | Done |
| PrivacyInfo + MAS / Developer ID / helper entitlements | Done |
| `--from-src` host-Python helper (local/CI) | Done |
| `--mas` frozen helper (required for Store; fail closed) | Done when PyInstaller present |
| `smoke_macos.sh` + security boundary tests | Done |
| Xcode Archive / ASC upload | **Operator-only** (full Xcode + Apple Distribution) |

## Requirements

- macOS 14+
- Xcode 15+ / Swift 5.9+ (CLT can ad-hoc build via `Scripts/build_app.sh`)
- For Store packaging: PyInstaller on the freeze machine
- For Archive/upload: full Xcode.app + Apple Distribution + ASC access

## Build

```bash
cd apps/macos
./Scripts/smoke_macos.sh           # CI-equivalent
./Scripts/build_app.sh --from-src  # local Prefer Bundled Helper
open build/RunSpecimen.app

# Mac App Store packaging (primary):
python3 -m pip install --user 'pyinstaller>=6'
./Scripts/build_app.sh --mas
```

Archive/upload when certs exist: `./Scripts/open_xcode.sh` then Product → Archive
(see APP_STORE.md). **Do not Submit for Review** without Codex QA + Yahor decision.

## Approval invariant

Approve attaches `runspecimen approve` to a **real PTY**. The app never types
`APPROVE` and never exposes an agent/plugin approval API.

## Non-goals

Not an OS sandbox for arbitrary payloads, job scheduler, compliance suite, or
asymmetric signature system. Certificates are hash-chained receipts.

## License

Apache-2.0 (same as the parent RunSpecimen project).
