# ASC kit status (honest)

App Store Connect queried **2026-09-18** via the App Store Connect API
(`GET /v1/apps?filter[bundleId]=com.darashkevich.runspecimen` and included
version/build/submission resources). Credentials are local-only; this file
records public Connect identifiers, not secrets.

## What Apple is reviewing (build 5)

`WAITING_FOR_REVIEW` means Apple has **build 5**, not “whatever is on PR #15.”
The ASC API does **not** store a git SHA. Identity below is reconstructed from
Connect timestamps + the git timeline.

| Connect field | Value |
| --- | --- |
| App | `6813492506` `RunSpecimen` `com.darashkevich.runspecimen` SKU `runspecimen-mac` |
| macOS version | **0.1.3** id `6cfe298b-92c1-460d-b83b-5687a67f2cff` `MAC_OS` `releaseType=AFTER_APPROVAL` |
| State | **WAITING_FOR_REVIEW** (not approved, not publicly available) |
| Submission | `appStoreVersionSubmissions` id `6cfe298b-92c1-460d-b83b-5687a67f2cff` |
| Build | **5** id `17c7d179-78e4-4b93-86ce-753cef186b20` `processingState=VALID` `expired=false` min OS 14.0 |
| Uploaded | `2026-09-18T06:38:17-07:00` (**15:38 CEST**) |
| pkg (Connect) | `0158194a-cc9c-419e-ae26-c6fb9be0e636.pkg` |
| Icon (Connect media) | 1024 App Store token, `hasPrerenderedIcon: true` (media ≠ compiled `Assets.car`) |

**Closest committed source:** `eba1abe` (PR #6 merge, 13:32 CEST) — the last
`main` commit **before** the upload. That tree is engine **`0.2.0rc10`**,
`CFBundleVersion` **4**, AppIcon via `Resources/AppIcon.icns` (no
`Assets.xcassets` catalog). Connect reports build **5**; git still said **4**.
Likely Xcode `manageAppVersionAndBuildNumber` (or an uncommitted local bump)
assigned 5 at export/upload. **Not** `ecc1709` / PR #15.

Commits that **cannot** be inside Apple’s binary (all after 15:38 CEST):

| Time (CEST) | Commit | Why it matters |
| --- | --- | --- |
| 16:15 | `2fe30c1` / `5234f7f` | Asset catalog (email-style filenames `icon_*@2x.png` / `*@email`) + git build **5** |
| 16:43 | `4f907c4` | Hexaflake mark across plugins + native AppIcon |
| 16:56 | `a4c007e` | Engine identity **0.2.0rc11** |
| 18:19 | `9fe2312` | Catalog filenames fixed; 128@2x is 256px; store-export `--verify --strict` |
| 18:30 | `ab2e07c` | Undersized on-screen windows sanitize to `minSize` |

### User-visible / safety-relevant diffs vs PR #15

| Surface | Build 5 (Apple) | PR #15 / this branch |
| --- | --- | --- |
| Frozen engine | **0.2.0rc10** (rc11 identity did not exist yet) | **0.2.0rc12** identity; freeze must match `__version__` |
| Incident bundle / remote-confirm refuse / `confirm_channel` | absent | present in engine |
| AppIcon in `.app` | icns from PR #6; no compiled catalog | hexaflake `Assets.car` + `icon_*@2x.png` with matching pixels |
| Window placement | no later clamp / `minSize` sanitize | tiny on-screen frames grow to minimum |
| Store export gate | not in the runtime binary | `--verify --strict` + tamper negatives (packaging) |
| Connect 1024 icon | present as media | still a separate Connect asset |

### Recommendation (Yahor decision — do not withdraw/resubmit from automation)

**Replace the binary after you decide.** Continuing this review means Apple
judges an rc10 helper, pre-hexaflake in-app icon, and the pre-clamp window
bugs. Waiting is cheaper than a review-notes surprise, but **do not cancel
WAITING_FOR_REVIEW** until you choose: keep this queue **or** reject/replace
with **0.1.3 (6)** built from the merged green tree.

This repo must not Submit, expire, or attach a new build without that decision.

## Packaging checklist (this operator Mac)

| Item | Status |
| --- | --- |
| Ad-hoc Archive + nested helper sandbox+inherit | Done (local) |
| Engine freeze | Archive path proven at **0.2.0rc11** on `44ddfed`; **next** freeze must be **0.2.0rc12** after the identity bump |
| PrivacyInfo + AppIcon | Done — catalog filenames are `icon_*@2x.png` with matching pixel sizes |
| Positive sandboxed e2e | Done via `Scripts/test_mas_sandbox_e2e.sh` — requires **actual** `Type 'APPROVE' to bind…` prompt + session still waiting; never types APPROVE |
| Store export fail-closed | Done — `codesign --verify --strict` on archived app + nested helper (tamper-after-signing refused) |
| Metadata / reviewer demo copy | Ready in this kit |
| ASC screenshot PNGs | **Captured** — 4 real app PNGs under [screenshots/](screenshots/) |
| Local e2e / gate evidence | [evidence/](evidence/) |
| Apple Distribution cert + MAS profile | **Present** (2026-09-18): `Apple Distribution: YAHOR DARASHKEVICH (UN6KF8636A)`; installer `3rd Party Mac Developer Installer: YAHOR DARASHKEVICH (UN6KF8636A)` in the keychain; profile `RunSpecimen MAS` UUID `0c5ef3dc-ebad-429b-8928-fdfcfee98c29` (`OSX`, `UN6KF8636A.com.darashkevich.runspecimen`, **one** Application `DeveloperCertificate`, no `get-task-allow`, no `ProvisionedDevices`). The profile **correctly omits** the installer cert (code-signing EKU vs installer EKU). Do **not** regenerate the app profile “to include” the installer identity. Developer ID Application is **not** a MAS substitute. |
| Distribution-signed archive | **Done** — `RS_MAS_EXPORT=0 ./Scripts/archive_mas.sh` from `/tmp/rs-clean-checkout` (`44ddfed`). App + helper `TeamIdentifier=UN6KF8636A`, Authority `Apple Distribution`, `codesign --verify --strict`, App Sandbox + helper inherit, `Assets.car` + `AppIcon.icns`. |
| Local MAS `.pkg` export | **Done** — `RS_EXPORT_DESTINATION=export` + `installerSigningCertificate` + profile **UUID** (display name `RunSpecimen MAS` is not what `exportArchive` resolves). Proof: [evidence/export-mas-local-pkg-ok.txt](evidence/export-mas-local-pkg-ok.txt). SHA-256 `e6ea0a7f12f4094ed430ea1ebc956ad6db2d67ecfa0f52e1eb0ebb66283f1bbf`. Extracted app **0.1.3 (5)** `mas`, both binaries `--verify --strict`, sandbox + inherit. **This local pkg is not what Apple is reviewing** (exported after PR #15 packaging fixes). First attempt without installer cert / UUID: [evidence/export-mas-local-pkg-installer-profile-mismatch.txt](evidence/export-mas-local-pkg-installer-profile-mismatch.txt). |
| `ExportOptions.mas.plist` committed `teamID` | Still placeholder `TEAMID`; `export_mas.sh` rewrites a temp copy (team ID + profile UUID). Default `destination=upload` — set `RS_EXPORT_DESTINATION=export` for a local pkg. Never `-allowProvisioningUpdates` without Yahor. |
| Next Connect upload | App **0.1.3** / **build 6** after Yahor replaces build 5 |

State ladder (do not collapse these):

1. **Uploaded** — build 5 is in Connect.
2. **Processing** — finished; `VALID`.
3. **Waiting for review** — current `appStoreState` / `appVersionState`.
4. **Approved** — not yet.
5. **Publicly available** — not yet (`AFTER_APPROVAL` will still need Apple to release it).

Do not merge/publish/submit from automation without Yahor’s release decision.
Do not treat WAITING_FOR_REVIEW as a live Mac App Store install.
