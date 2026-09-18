# ASC kit status (honest)

Last packaging tip should match PR #6 / `cursor/macos-native-app`.
App Store Connect queried **2026-09-18T16:17Z** via the App Store Connect API
(`GET /v1/apps?filter[bundleId]=com.darashkevich.runspecimen` and included
version/build/submission resources). Credentials are local-only; this file
records public Connect identifiers, not secrets.

| Item | Status |
| --- | --- |
| Ad-hoc Archive + nested helper sandbox+inherit | Done (local) |
| Engine freeze **0.2.0rc11** (app **0.1.3**) | Done on archive path |
| PrivacyInfo + AppIcon | Done — catalog filenames are `icon_*@2x.png` with matching pixel sizes |
| Positive sandboxed e2e (bookmark / dashboard / PTY wait) | Done via `Scripts/test_mas_sandbox_e2e.sh` — requires **actual** `Type 'APPROVE' to bind…` prompt + session still waiting; never types APPROVE |
| Store export fail-closed | Done — `codesign --verify --strict` on archived app + nested helper (tamper-after-signing refused); app path derived from `RS_ARCHIVE_PATH`; `RS_TEST_CODESIGN_DV_*` harness-only; `test_store_export_gate.sh` negatives prove unsigned / tamper / ad-hoc / Developer ID / bypass / fixtures refused before `xcodebuild -exportArchive` |
| Metadata / reviewer demo copy | Ready in this kit |
| ASC screenshot PNGs | **Captured** — 4 real app PNGs under [screenshots/](screenshots/) (ad-hoc MAS; e2e demo path; see caveats in screenshots README) |
| Local e2e / gate evidence | [evidence/](evidence/) — PTY + store-export negatives (not Connect media) |
| Apple Distribution cert + MAS profile | **Present on this operator Mac** (2026-09-18): application identity `Apple Distribution: YAHOR DARASHKEVICH (UN6KF8636A)`; installer identity `3rd Party Mac Developer Installer: YAHOR DARASHKEVICH (UN6KF8636A)` also in the keychain; profile `RunSpecimen MAS` (`OSX`, `UN6KF8636A.com.darashkevich.runspecimen`, no `get-task-allow`, no `ProvisionedDevices`). Developer ID Application is **not** a MAS substitute. |
| Distribution-signed archive (clean checkout `44ddfed`) | **Done** — `RS_MAS_EXPORT=0 ./Scripts/archive_mas.sh` from `/tmp/rs-clean-checkout`. App + helper `TeamIdentifier=UN6KF8636A`, Authority `Apple Distribution`, `codesign --verify --strict` on both, App Sandbox + helper inherit, engine `0.2.0rc11`, `Assets.car` + `AppIcon.icns` present. Store export gate `READY_TEAM=UN6KF8636A`. |
| Local MAS `.pkg` export | **Blocked** — `xcodebuild -exportArchive` with `destination=export` (no upload) failed: profile `RunSpecimen MAS` does not include installer cert `3rd Party Mac Developer Installer: YAHOR DARASHKEVICH (UN6KF8636A)`. Automatic export wants `-allowProvisioningUpdates` (not used; no portal credential handling). **Not a substitute:** this is not a Store-ready pkg. Connect already has valid build **5** waiting for review. |
| `ExportOptions.mas.plist` committed `teamID` | Still placeholder `TEAMID` in git; export path rewrites locally when a real team is resolved |
| ASC app record | **Exists** — app id `6813492506`, name `RunSpecimen`, bundle `com.darashkevich.runspecimen`, SKU `runspecimen-mac` |
| Upload / processing | **Done** — build **5** id `17c7d179-78e4-4b93-86ce-753cef186b20`, `processingState=VALID`, uploaded `2026-09-18T06:38:17-07:00`, `expired=false`, min OS 14.0 |
| Submit for Review | **Already submitted** — `appStoreVersionSubmissions` id `6cfe298b-92c1-460d-b83b-5687a67f2cff` is attached to macOS version `0.1.3` |
| App Store version state | **WAITING_FOR_REVIEW** (not approved, not publicly available). Version id `6cfe298b-92c1-460d-b83b-5687a67f2cff`, platform `MAC_OS`, `releaseType=AFTER_APPROVAL`. Selected build is **5** (`VALID`). |
| App Review approval | **Not approved** |
| Mac App Store public listing | **No public URL** — do not add a MAS link on the product page until Apple returns a live `apps.apple.com` URL |

State ladder (do not collapse these):

1. **Uploaded** — build 5 is in Connect.
2. **Processing** — finished; `VALID`.
3. **Waiting for review** — current `appStoreState` / `appVersionState`.
4. **Approved** — not yet.
5. **Publicly available** — not yet (`AFTER_APPROVAL` will still need Apple to release it).

Do not merge/publish/submit from automation without Yahor’s release decision.
Do not treat WAITING_FOR_REVIEW as a live Mac App Store install.
