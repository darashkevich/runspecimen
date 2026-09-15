# Embedded helper (optional — Mac App Store stretch)

Stub + build wiring for shipping a signed `runspecimen` engine inside the app
bundle so Target A (Mac App Store) does not depend on a user-installed PyPI tool
(guideline **2.4.5(viii)** risk).

**Status (2026-09-15):** discovery order wired in `CLIService` / `AppModel`;
`Scripts/build_app.sh` always creates `Contents/Helpers/`; staging helper via
`Scripts/stage_helper.sh`. **No frozen helper binary ships in-repo yet** —
packaging + Developer ID signing remain blocked without Apple certs.

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
    runspecimen              # signed executable entry (when staged)
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
active **Source** label.

## What this stub includes now

- `Helpers/README.md` (this file)
- `Helpers/.gitkeep` so the directory is tracked
- `Helpers/payload/` gitignored — place local build artifacts here during experiments
- `Scripts/stage_helper.sh` — layout + exact packaging steps; `--from PATH` to stage
- `Scripts/build_app.sh` — copies `payload/runspecimen` → `Contents/Helpers/` when present
- `Entitlements/RunSpecimen.helper.entitlements` — inherit sandbox for child helper
- App discovery + Settings source label (ADR-002)

## Exact next packaging steps

Run `./Scripts/stage_helper.sh` for the live checklist. Summary:

1. Choose packaging: PyInstaller / python-build-standalone + zipapp / future compiled helper.
2. License audit of bundled runtime (Apache-2.0 app; runtime licenses must be redistributable).
3. Place executable at `Helpers/payload/runspecimen` (or `--from`).
4. codesign helper with `RunSpecimen.helper.entitlements` + same Team ID as the app.
5. `./Scripts/build_app.sh` then `./Scripts/sign_and_notarize.sh all` (needs Developer ID).
6. Confirm Settings → Source = “Bundled Helpers”.
7. Update App Review notes in APP_STORE.md with helper path + demo instructions.

## Non-goals for this stub

- Do not weaken interactive approval.
- Do not add analytics, crash uploaders, or network “phone home.”
- Do not `pip install` into shared site-packages from the app (2.4.5(ii)).
- Do not claim the helper is an OS sandbox or that receipts are digital signatures.
