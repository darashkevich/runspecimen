# RunSpecimen for macOS

Native SwiftUI companion for [RunSpecimen](https://github.com/darashkevich/runspecimen) —
a local safety and evidence layer for one human-approved bounded run at a time.

This app is a **thin shell** over the CLI enforcement engine. It does not reimplement
leases, approval binding, or receipt verification in Swift.

## Distribution stance

See **[APP_STORE.md](APP_STORE.md)** and **[docs/ADR-001-architecture.md](docs/ADR-001-architecture.md)**.

- **v1 ship:** Developer ID + notarization (Target B), sandbox-compatible code paths.
- **Stretch:** Mac App Store (Target A) after review-risk mitigation / optional embedded helper.

## What works in this scaffold

| Capability | Status |
| --- | --- |
| Brand-first empty state, flight-ops theme | Done |
| Workspace picker via Open panel + security-scoped bookmarks | Done |
| CLI path via Open panel (sandbox-safe) + optional PATH probe (non-sandbox) | Done |
| `doctor`, `--version`, `status`, `validate` integration | Done |
| Lifecycle status + evidence / receipt inspector (read-only) | Done |
| Action bar gating (approve / run / postflight / verify / dashboard) | Done |
| Open loopback dashboard (`dashboard --open`) | Done |
| Approve sheet with real PTY → `runspecimen approve` | Scaffold (requires build host PTY) |
| Settings (CLI path, version, privacy, non-goals) | Done |
| App Sandbox entitlements + PrivacyInfo | Done |
| Notarized / MAS archive | Blocked without full Xcode + signing identity |

## Requirements

- macOS 14+
- Xcode 15+ recommended for Archive (Command Line Tools can compile sources via `Scripts/build_app.sh`)
- Installed `runspecimen` CLI (PyPI `runspecimen` or this repo’s `pip install .`)

```bash
python3 -m pip install 'runspecimen==0.2.0rc9'
# or from this repository:
# sh scripts/bootstrap_dev.sh
runspecimen --version
```

## Build

```bash
cd apps/macos
./Scripts/build_app.sh          # produces build/RunSpecimen.app
open build/RunSpecimen.app
```

With full Xcode, open `Package.swift` / generate an Xcode project and Archive with the
desired entitlements file (`Entitlements/RunSpecimen.mas.entitlements` or
`.developer-id.entitlements`).

## Approval invariant

Human approval remains interactive. The Approve sheet attaches `runspecimen approve` to a
**real PTY** so the engine’s `isatty` gate still holds. The app never types `APPROVE` for
the user and never offers an agent/plugin approval channel.

## Non-goals (also shown in-app)

Not an OS sandbox, job scheduler, compliance suite, or asymmetric signature system.
Certificates are locally verifiable hash-chained receipts — not digital signatures.

## License

Apache-2.0 (same as the parent RunSpecimen project).
