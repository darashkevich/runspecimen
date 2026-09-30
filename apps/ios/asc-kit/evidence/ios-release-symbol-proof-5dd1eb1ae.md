# iOS Observe Release symbol proof (local QA)

**Not a production sign-off.** Not a device archive, TestFlight upload, or App Store submission.

| Field | Value |
| --- | --- |
| Source tip inspected | `5dd1eb1ae06576de930a03160a85a1135458ee0d` (`cursor/integrated-release-candidate`) |
| When | 2026-09-30 (UTC) |
| Host | Darwin 27.0.0 arm64 |
| Xcode | Xcode 27.0 Build version 27A266a  |
| Script | `apps/ios/Scripts/verify_ios_release_symbols.sh` |
| Destination | `generic/platform=iOS Simulator` |
| DerivedData | `/tmp/rs-ios-nm-verify-run` |
| Result | **PASS** |

## What this proves

Shipping target `RunSpecimenObserve` Release:

- Does **not** compile `DevelopmentCompanionSigner.swift` (Dev target only).
- Does **not** define `RUNSPECIMEN_TEST_HOOKS` (Debug does, because it hosts unit tests).
- `nm -Uj` on the Release app binary and on `CompanionSecureEnclaveEnrollment.o` has **empty** matches for:
  - `beforeConsumptionDecision`
  - `beforeExclusiveAccess`
  - `beforeFinalSignatureDecision`
  - `retireUnusableKey`

Debug contrast (same project, `RUNSPECIMEN_TEST_HOOKS` on): `beforeFinalSignatureDecision` **is** present in `RunSpecimenObserve.debug.dylib` and in Debug `CompanionSecureEnclaveEnrollment.o`. The other three names are not part of the Observe sources (they live in macOS `BiometricApproval`); they stay absent on both configs here.

## Commands

```bash
bash apps/ios/Scripts/verify_ios_release_symbols.sh
# RS_IOS_DERIVED_DATA=/tmp/rs-ios-nm-verify-run RS_IOS_NM_COMPARE_DEBUG=1
```

Release empty matches (expect no lines after each `grep`):

```bash
BIN=/tmp/rs-ios-nm-verify-run/Build/Products/Release-iphonesimulator/RunSpecimenObserve.app/RunSpecimenObserve
OBJ=/tmp/rs-ios-nm-verify-run/Build/Intermediates.noindex/RunSpecimenObserve.build/Release-iphonesimulator/RunSpecimenObserve.build/Objects-normal/arm64/CompanionSecureEnclaveEnrollment.o

nm -Uj "$BIN" | grep -F beforeConsumptionDecision || true
# (empty)

nm -Uj "$BIN" | grep -F beforeExclusiveAccess || true
# (empty)

nm -Uj "$BIN" | grep -F beforeFinalSignatureDecision || true
# (empty)

nm -Uj "$BIN" | grep -F retireUnusableKey || true
# (empty)

nm -Uj "$OBJ" | grep -F beforeFinalSignatureDecision || true
# (empty)
```

Observed Release `nm -Uj` line counts: app binary **2945**, arm64 `CompanionSecureEnclaveEnrollment.o` **315**. Forbidden match counts: all **0**.

Debug contrast (present):

```bash
DYLIB=/tmp/rs-ios-nm-verify-run/Build/Products/Debug-iphonesimulator/RunSpecimenObserve.app/RunSpecimenObserve.debug.dylib
nm -Uj "$DYLIB" | grep -F beforeFinalSignatureDecision | head
# _$s18RunSpecimenObserve32CompanionSecureEnclaveEnrollmentO28beforeFinalSignatureDecision_WZ
# … (10 defined symbols)
```

## Script summary (trimmed)

```
pbxproj: shipping Observe Sources exclude DevelopmentCompanionSigner; Release omits RUNSPECIMEN_TEST_HOOKS
==> nm -Uj (Release app)
  defined_symbol_lines: 2945
  match[beforeConsumptionDecision]=0
  match[beforeExclusiveAccess]=0
  match[beforeFinalSignatureDecision]=0
  match[retireUnusableKey]=0
==> nm -Uj (Release module objects)
  match[*]=0
ok: Release has empty nm -Uj matches for forbidden + DevelopmentCompanionSigner
ok: Debug contrast — beforeFinalSignatureDecision present in …/RunSpecimenObserve.debug.dylib
==> verify_ios_release_symbols: PASS
note: simulator Release build; not a device archive or App Store sign-off
```

## Limits

- Simulator Release with `CODE_SIGNING_ALLOWED=NO`, not an Apple Distribution device archive.
- Does not exercise Face ID, pairing, or APPROVE.
- CI job: `ios-release-symbols` in `.github/workflows/ci.yml`.
