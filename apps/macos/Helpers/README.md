# Embedded helper — Mac App Store primary path

Ship a **self-contained** `runspecimen` engine inside
`RunSpecimen.app/Contents/Helpers/` so Mac App Store builds do not depend on a
user-installed PyPI/Python tool (guideline **2.4.5(viii)**).

**Status:** MAS packaging is **`./Scripts/build_app.sh --mas`** — PyInstaller
freeze into a Mach-O helper, **fail closed** if freeze is impossible. Host-Python
`--from-src` remains for local/CI Prefer Bundled Helper tests only.

## Goals

| Goal | Constraint |
| --- | --- |
| Self-contained MAS submission | Frozen Mach-O under `Contents/Helpers/runspecimen` |
| Same enforcement boundary | Helper is the real CLI, not a Swift reimplementation |
| Preserve TTY approval | Approve still uses a real PTY; **never** auto-type `APPROVE` |
| No telemetry | Helper inherits local-only invariant |
| Honest crypto / sandbox copy | Receipts ≠ digital signatures; UI sandbox ≠ payload OS sandbox |

## Layout

```
RunSpecimen.app/Contents/
  MacOS/RunSpecimen          # SwiftUI shell
  Resources/AppIcon.icns
  Helpers/
    runspecimen              # MAS: frozen Mach-O; local: launcher or freeze
    lib/runspecimen/         # ONLY for --from-src (forbidden in --mas)
    NOTICE.txt
  Resources/PrivacyInfo.xcprivacy
```

Entitlements:

- App: `Entitlements/RunSpecimen.mas.entitlements` (Store) or developer-id twin
- Helper: `Entitlements/RunSpecimen.helper.entitlements` (`app-sandbox` + `inherit`)
  — applied by `Scripts/sign_nested_helper.sh` using the real Xcode/keychain
  identity when present; ad-hoc `-` only for local smoke (TeamIdentifier unset).
  Inherit-signed helpers intentionally fail when launched from an unsandboxed
  shell; gate `--version` on `Helpers/payload/` before nested sign.

## Discovery order

1. Security-scoped bookmark from Open panel (user override).
2. Bundled `Contents/Helpers/runspecimen` if executable (size ≥ 64 bytes).
3. PATH / PyPI locations — **Developer ID / local only** (disabled when
   `RSDistributionChannel=mas`).

MAS runtime **rejects** shell-script host-Python launchers and fails closed if
the frozen helper is missing.

## Packaging modes

| Mode | Command | Host Python? | MAS? |
| --- | --- | --- | --- |
| Frozen (required for Store) | `./Scripts/build_app.sh --mas` | No | **Yes** |
| Frozen (optional local) | `./Scripts/build_app.sh --frozen-helper` | No if freeze works | Prep |
| Package tree | `./Scripts/build_app.sh --from-src` | **Yes** | No |

```bash
# Mac App Store packaging (fail closed without PyInstaller)
python3 -m pip install --user 'pyinstaller>=6'
./Scripts/build_app.sh --mas
build/RunSpecimen.app/Contents/Helpers/runspecimen --version
test ! -d build/RunSpecimen.app/Contents/Helpers/lib

# Local Prefer Bundled Helper (CI default)
./Scripts/stage_helper.sh --from-src --verify
./Scripts/build_app.sh
```

## License notes

- RunSpecimen package: Apache-2.0, `dependencies = []`.
- PyInstaller bootloader: Apache-2.0; bundled CPython needs NOTICE attribution
  (written into `Helpers/payload/NOTICE.txt` / `Contents/Helpers/NOTICE.txt`).
- Never commit `Helpers/payload/`.

## Non-goals

- Do not weaken interactive approval or add telemetry.
- Do not `pip install` into shared site-packages from the app.
- Do not claim the helper or UI sandbox is an OS sandbox for arbitrary payloads.
