# Embedded helper (optional — Mac App Store stretch)

Stub + build wiring for shipping a signed `runspecimen` engine inside the app
bundle so Target A (Mac App Store) does not depend on a user-installed PyPI tool
(guideline **2.4.5(viii)** risk).

**Status (2026-09-15):** discovery order wired in `CLIService` / `AppModel`;
`Scripts/build_app.sh` always creates `Contents/Helpers/`; staging via
`Scripts/stage_helper.sh --from-src` (Apache-2.0 stdlib-only package tree +
host-Python launcher). **No frozen CPython/PyInstaller binary ships in-repo** —
full self-containment + Developer ID signing remain blocked without Apple certs.

## Goals

| Goal | Constraint |
| --- | --- |
| Self-contained MAS submission | Helper lives under `RunSpecimen.app/Contents/Helpers/` |
| Same enforcement boundary | Helper is the real CLI (or a thin launcher to it), not a Swift reimplementation |
| Preserve TTY approval | Approve still uses a real PTY; **never** auto-type `APPROVE` |
| No telemetry | Helper inherits local-only invariant |
| Honest crypto copy | Receipts remain hash-chained / HMAC — not asymmetric “digital signatures” |

## Layout

```
RunSpecimen.app/Contents/
  MacOS/RunSpecimen          # SwiftUI shell
  Helpers/
    runspecimen              # launcher (or frozen binary) when staged
    lib/runspecimen/         # package tree when staged via --from-src
    NOTICE.txt               # Apache-2.0 / packaging notes
    README.md                # placeholder when no helper staged
  Resources/…
```

Entitlement posture:

- App keeps App Sandbox + `user-selected.*` for workspaces.
- Helper uses `Entitlements/RunSpecimen.helper.entitlements`
  (`com.apple.security.inherit`) when spawned as a child.
- Avoid Hardened Runtime exceptions unless the embedded interpreter requires
  them — any exception must be listed in APP_STORE.md before enablement.

## Discovery order (implemented)

`CLIService` / bootstrap resolve in this order:

1. Security-scoped bookmark from Open panel (always valid; user override).
2. Bundled `Contents/Helpers/runspecimen` if present **and executable** (size ≥ 64 bytes).
3. PATH / PyPI common locations (Developer ID / local debug only).

MAS builds should prefer (1) or (2) and not rely on (3). Settings shows the
active **Source** label. Use **Engine → Prefer Bundled Helper** (or Settings)
to clear the bookmark and force (2) when testing a staged helper.

## License / packaging decision

| Option | License story | Status |
| --- | --- | --- |
| `--from-src` package tree + host Python 3.9+ launcher | Redistributes only Apache-2.0 project code (`dependencies = []`) | **Implemented** — preferred for local / Target B experiments |
| `--from PATH` copy of installed CLI | Same code license; shebang may be machine-local | Dry-run only |
| PyInstaller onefile (optional) | Bootloader Apache-2.0; must attribute bundled CPython | `Scripts/freeze_helper.sh` behind `RS_FREEZE_HELPER=1` — **local unsigned freeze verified** on this Mac; skips cleanly if PyInstaller absent. Shipping still needs Developer ID + NOTICE audit |

## What this stub includes now

- `Helpers/README.md` (this file)
- `Helpers/.gitkeep` so the directory is tracked
- `Helpers/payload/` gitignored — place local build artifacts here during experiments
- `Scripts/stage_helper.sh` — `--from-src`, `--from`, `--check`, `--verify`
- `Scripts/freeze_helper.sh` — optional PyInstaller onefile (`RS_FREEZE_HELPER=1`); exit 0 when absent
- `Scripts/build_app.sh` — copies launcher + `lib/` + NOTICE → `Contents/Helpers/`
- `Entitlements/RunSpecimen.helper.entitlements` — inherit sandbox for child helper
- App discovery + Settings / Engine menu source controls (ADR-002)
- Prefer Bundled Helper clears the CLI bookmark without re-persisting PATH probes

## Exact next packaging steps

```bash
./Scripts/stage_helper.sh --from-src --verify
./Scripts/build_app.sh
# Confirm: build/RunSpecimen.app/Contents/Helpers/runspecimen --version
# In-app: Engine → Prefer Bundled Helper → Source = “Bundled Helpers”
```

Or one-shot: `./Scripts/build_app.sh --from-src`

### Optional freeze end-to-end (`RS_FREEZE_HELPER=1`)

Not CI-default. Local experiment / MAS stretch prep. Still needs Developer ID to ship.

```bash
python3 -m pip install --user 'pyinstaller>=6'   # local only
RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh --verify
./Scripts/build_app.sh
build/RunSpecimen.app/Contents/Helpers/runspecimen --version
# Expect Mach-O helper; no Contents/Helpers/lib/ tree
```

One-shot with automatic fallback when PyInstaller is missing:

```bash
./Scripts/build_app.sh --frozen-helper
# Logs “Using frozen helper…” or “falling back to stage_helper.sh --from-src”
```

Without PyInstaller or without `RS_FREEZE_HELPER=1` / `--frozen-helper`, freeze is skipped
(exit 0) so CI stays green. Operator checklist: [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md).
Codesign the frozen Mach-O with inherit entitlements, then notarize (needs Developer ID).
## Non-goals for this stub

- Do not weaken interactive approval.
- Do not add analytics, crash uploaders, or network “phone home.”
- Do not `pip install` into shared site-packages from the app (2.4.5(ii)).
- Do not claim the helper is an OS sandbox or that receipts are digital signatures.
