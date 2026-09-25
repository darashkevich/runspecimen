# APP_STORE.md — Mac App Store submission (primary)

Primary ship target for the RunSpecimen macOS companion (`apps/macos`) is the
**Mac App Store**. Developer ID notarization remains a secondary / direct-download
path — see [NOTARIZATION.md](NOTARIZATION.md).

Consult current Apple docs before each submission:

- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) (esp. **2.4.5**, **2.5.1**, **4.2**, **5.1**)
- [App Sandbox](https://developer.apple.com/documentation/security/app_sandbox)
- [Accessing files from the macOS App Sandbox](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox)
- [Privacy manifest files](https://developer.apple.com/documentation/bundleresources/privacy_manifest_files)
- [Uploading apps](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds)

## Recommendation (current)

| Channel | Role | Verdict |
| --- | --- | --- |
| **Target A — Mac App Store** | **Primary** | `./Scripts/build_app.sh --mas` (a future frozen helper **must match** `src/runspecimen/__version__`, now **0.2.0rc14**; build 8 froze **0.2.0rc12** and stays in review) → `./Scripts/archive_mas.sh` → `RS_EXPORT_DESTINATION=export ./Scripts/export_mas.sh` for a local Store pkg, or default destination `upload` after Yahor decides |
| **Target B — Developer ID + notarization** | Secondary / direct download | Optional after MAS; same sandbox entitlements preferred. **Not** a Store-validation substitute |

### Why MAS-first now

1. **Guideline 2.4.5(viii)** — Store builds embed a **frozen Mach-O** helper
   (`Contents/Resources/RunSpecimenEngine/`, PyInstaller **onedir** + `_internal/`)
   built from the current engine (`0.2.0rc14` on this branch). **Onefile is not used**
   — its bootloader needs SysV semaphores denied by App Sandbox. No host Python /
   optionally installed PyPI CLI is required for Store builds. `--from-src`
   host-Python launchers are **local/CI only** and are rejected at runtime when
   `RSDistributionChannel=mas`.
2. **Guideline 2.4.5(i)** — App Sandbox + justified entitlements
   (`Entitlements/RunSpecimen.mas.entitlements`).
3. **Guideline 2.4.5(ii)** — Self-contained `.app`; never `pip install` into shared
   locations from the app.
4. **Guideline 4.2** — Native SwiftUI control surface (status, evidence, PTY approve),
   not a web clipping. Screenshots must lead with native UX.

Honest security copy (required): App Sandbox confines the UI (+ inherit helper).
It does **not** OS-sandbox the payload under test. See
[docs/SECURITY_BOUNDARY.md](docs/SECURITY_BOUNDARY.md).

## Operator-only prerequisites (remaining)

| Prerequisite | Why |
| --- | --- |
| **Apple Developer Program** membership | Identifiers, profiles, App Store Connect |
| **Apple Distribution** certificate + Mac App Store provisioning profile | Codesign for Store upload |
| App Store Connect **API key** (or Apple ID + app-specific password) | Upload / metadata |
| ASC app record: bundle id `com.darashkevich.runspecimen`, screenshots, privacy URL | Review |

**Xcode status (this Mac):** Xcode **27.0** is installed and selected
(`xcode-select` → `/Applications/Xcode.app/...`). `./Scripts/archive_mas.sh`
produces a real Archive. When no Apple identity is in the keychain, nested
helper + app signing is **ad-hoc** (TeamIdentifier unset) but still applies
`RunSpecimen.helper.entitlements` (App Sandbox + inherit) — labeled as local
structural smoke only. **Upload / Submit for Review** still need Yahor’s Apple
Distribution identity + ASC (nested sign then uses that identity/team).

Optional local tool: `brew install xcodegen` to refresh `RunSpecimen.xcodeproj`
from `project.yml` (`./Scripts/generate_xcodeproj.sh`). A generated project is
committed so Archive works without regenerating.

## Build / Archive / Upload

```bash
cd apps/macos
python3 -m pip install --user 'pyinstaller>=6'   # freeze machine only
./Scripts/verify_app_icon.sh
./Scripts/test_security_boundary.sh
./Scripts/build_app.sh --mas
# Confirm helper is current engine (rc12 on this branch):
#   Helpers/payload/runspecimen --version   # gate BEFORE inherit sign
#   codesign -d --entitlements - Contents/Resources/RunSpecimenEngine/runspecimen
#   # Do NOT expect engine --version from a normal shell —
#   # inherit-signed helpers exit non-zero outside the parent app sandbox (by design).
#   Contents/Resources/RunSpecimenEngine/_internal/ present (onedir)
#   no Contents/Helpers/lib/ (host-Python tree)
#   no Contents/Helpers/_internal (data must not live under Helpers — breaks codesign)
#   Info.plist RSDistributionChannel == mas
#   Resources/AppIcon.icns present

# Archive (ad-hoc when no Apple Distribution identity; real identity when present):
./Scripts/archive_mas.sh
# Fail-closed assertions (signature, entitlements, team/adhoc, sandbox probe, PTY):
#   ./Scripts/assert_archive_signing.sh /path/to/RunSpecimen.app [--expect-adhoc|--expect-team TEAM]
# Or open Xcode:
./Scripts/open_xcode.sh
#   Signing & Capabilities: Team + App Sandbox + MAS entitlements (for ASC)
#   Product → Archive → Distribute App → App Store Connect → Upload
```

Export options template: [Config/ExportOptions.mas.plist](Config/ExportOptions.mas.plist)
(committed `teamID` stays `TEAMID`; `export_mas.sh` rewrites a temp copy).
**Fail-closed export:** `./Scripts/assert_store_export_ready.sh` then
`./Scripts/export_mas.sh` — Apple Distribution + matching team + MAS profile +
**app inside `RS_ARCHIVE_PATH`** (app + nested helper Distribution-signed via
real `codesign -dv`) required; **`RS_ARCHIVE_APP` must match that archive path**
(mismatched overrides refused); **Developer ID / ad-hoc archives and
`RS_TEST_CODESIGN_DV_*` fixtures are not sufficient** for production export.

### Why the MAS profile omits `3rd Party Mac Developer Installer`

That is **expected**. A Mac App Store **app** provisioning profile embeds the
**Apple Distribution (Application)** certificate (code-signing EKU). The
**installer** certificate (`3rd Party Mac Developer Installer`) signs the
`.pkg` wrapper and is **not** listed in `DeveloperCertificates` of
`RunSpecimen MAS`. Regenerating the app profile will not add it. Do **not**
enable `-allowProvisioningUpdates` / portal automation without Yahor.

Operator steps (once per machine; no credential handling in git):

1. Developer → Certificates: keep **Apple Distribution** (Application) and
   **3rd Party Mac Developer Installer** installed in the login keychain
   (`security find-identity -v -p codesigning` plus
   `security find-identity -v | grep 'Mac Developer Installer'`).
2. Developer → Profiles: Mac App Store **App Store** profile named
   `RunSpecimen MAS` for `UN6KF8636A.com.darashkevich.runspecimen`,
   Distribution (not Development). Download. On Xcode 16+ it lands as
   `~/Library/Developer/Xcode/UserData/Provisioning Profiles/<UUID>.provisionprofile`
   (the empty `~/Library/MobileDevice/Provisioning Profiles` dir is a red herring).
3. Confirm the decoded profile has **one** Application `DeveloperCertificate`,
   no `get-task-allow`, no `ProvisionedDevices`, platform `OSX`.
4. Archive: `./Scripts/archive_mas.sh` (Manual Apple Distribution + team;
   do not attach the MAS profile to `RunSpecimenCore`).
5. Local Store pkg (no upload):
   `RS_EXPORT_DESTINATION=export ./Scripts/export_mas.sh`
   `export_mas.sh` sets `installerSigningCertificate=3rd Party Mac Developer Installer`
   and rewrites `provisioningProfiles` to the profile **UUID** (`exportArchive`
   does not resolve the display name `RunSpecimen MAS`).
6. Verify: `pkgutil --check-signature` (installer chain), then extract and
   `codesign --verify --strict` the `.app` and nested helper; entitlements
   sandbox + inherit; `RSDistributionChannel=mas`.
7. The recorded submission is **0.1.4 (9)**. Do not upload another build or Submit for Review from this script while that submission is the one on file. **0.1.3 (8)** was rejected.

ASC paste pack (metadata / screenshots checklist / reviewer demo):
[asc-kit/](asc-kit/) — mark screenshot PNGs and Connect record as **pending** until Yahor fills them.

## Nested signing (helper)

`Contents/Helpers/runspecimen` is signed **inside-out** before the outer `.app` seal:

| Mode | Identity | Helper entitlements | TeamIdentifier |
| --- | --- | --- | --- |
| Local structural smoke (no certs) | ad-hoc `-` (labeled) | `app-sandbox` + `inherit` | not set |
| Apple Distribution / Development | Xcode / `RS_SIGN_IDENTITY` / keychain | same | team from identity |

Scripts: `Scripts/resolve_codesign_identity.sh`, `Scripts/sign_nested_helper.sh`.
Xcode build phases **Embed Frozen Helper** and **Clear Codesign Xattrs** call
`sign_nested_helper.sh` — they must **not** hard-code `codesign --sign -`.

## Entitlements

### Target A — Mac App Store (`Entitlements/RunSpecimen.mas.entitlements`)

| Entitlement | Purpose |
| --- | --- |
| `com.apple.security.app-sandbox` | Required for MAS (2.4.5(i)) |
| `com.apple.security.files.user-selected.read-write` | Workspace + evidence via Open panel |
| `com.apple.security.files.user-selected.executable` | Execute user-picked CLI override (optional; Store prefers bundled helper) |
| `com.apple.security.network.client` | Optional docs links (GitHub / privacy) in browser; no telemetry |

Store builds intentionally omit `com.apple.security.network.server` (guideline
2.4.5(i) — Apple rejected it when unused). The optional loopback browser
dashboard is hidden/refused on MAS; native evidence views remain. Developer ID
builds may still use `network.server` for the local dashboard.

Helper child: `Entitlements/RunSpecimen.helper.entitlements` (`app-sandbox` + `inherit`).
Applied on every MAS / frozen Mach-O nested sign (including ad-hoc local archives).

Do **not** enable: camera, mic, contacts, location, Apple Events automation,
`get-task-allow` in release.

### Target B — Developer ID

Same sandbox entitlements preferred. Hardened Runtime via
`codesign --options runtime` (see NOTARIZATION.md). Not the primary path.

## Privacy

### App Privacy (App Store Connect)

Declare **Data Not Collected** while true: no analytics, crash uploaders, ads,
accounts, or phone-home.

### In-app privacy policy (5.1.1)

Settings → Privacy, Help → Privacy Policy, About →
https://runspecimen.darashkevich.com/privacy/ (+ GitHub `SECURITY.md`).

### `PrivacyInfo.xcprivacy`

Shipped under `Resources/PrivacyInfo.xcprivacy`:

- `NSPrivacyTracking` = false
- `NSPrivacyCollectedDataTypes` = []
- Required-reason APIs: `UserDefaults` → `CA92.1` (bookmarks / last workspace)

## Identity / version

| Key | Value |
| --- | --- |
| Bundle ID | `com.darashkevich.runspecimen` |
| Display name | RunSpecimen |
| Category | Developer Tools |
| Short version | `0.1.3` (bump per ship) |
| Build | `8` in review (builds **5**–**6** rejected; **7** uploaded then superseded) |
| Min macOS | 14.0 |
| Bundled engine | source `__version__` is `0.2.0rc14`; build 8 in review froze `0.2.0rc12` |
| Icon | `Resources/AppIcon.icns` (+ iconset / 1024 for Connect) |

## Review notes (paste into App Review)

> Launch RunSpecimen. The Store build opens the bundled Reviewer Demo
> automatically. Source should read Bundled Helpers — do not pip install.
> Inspect status, then type APPROVE yourself on the PTY. The app never
> auto-approves. App Sandbox confines the UI (+ inherit helper); it does not
> OS-sandbox the payload under test. Data Not Collected.

### Demo path for reviewers

1. Launch RunSpecimen — bundled helper + Reviewer Demo workspace open automatically (Source = “Bundled Helpers”).
2. Use **Open Reviewer Demo** only if you need a fresh copy.
3. Refresh status / inspect certificate (read-only).
4. Open Approve sheet — type `APPROVE` yourself on the PTY (do not automate).
5. Quit — confirm dashboard child is gone.

Provide a sample workspace zip in Review notes if the showcase tree is not in the build.

## Screenshots / metadata checklist

- [x] 1280×800 (or current ASC sizes) showing Main Console with brand + status (not Terminal) — [asc-kit/screenshots/01-main-console-1280x800.png](asc-kit/screenshots/01-main-console-1280x800.png)
- [x] Approve sheet visible (human PTY, no auto-fill) — [asc-kit/screenshots/02-approve-sheet-pty-1280x800.png](asc-kit/screenshots/02-approve-sheet-pty-1280x800.png)
- [x] Settings / Privacy + About privacy-policy link — [asc-kit/screenshots/03-settings-privacy.png](asc-kit/screenshots/03-settings-privacy.png), [04-about-privacy-links-1280x800.png](asc-kit/screenshots/04-about-privacy-links-1280x800.png)
- [ ] App icon: opaque `#070A0F` field, **not** pre-rounded (`AppIcon-1024.png`)
- [ ] Subtitle / description: local evidence control — not “OS sandbox for malware”
- [ ] Support URL: https://runspecimen.darashkevich.com/support/
- [ ] Privacy URL: https://runspecimen.darashkevich.com/privacy/
- [ ] Export compliance: HTTPS docs links only → standard answers

## Rejection risks & mitigations

| Risk | Guideline | Mitigation |
| --- | --- | --- |
| Optionally installed Python/CLI | 2.4.5(viii) | Frozen helper required for `--mas`; fail closed |
| Thin wrapper | 4.2 | Lead with native status/evidence/Approve UX |
| Arbitrary executable | Sandbox | Basename `runspecimen` + version gate; Store prefers bundled helper |
| Misleading security claims | 2.3 | SECURITY_BOUNDARY.md; honest copy |
| Background dashboard after quit | 2.4.5(iii) | Kill dashboard child on terminate |
| Private APIs | 2.5.1 | Public AppKit/SwiftUI/Foundation/Darwin PTY only |
| Telemetry contradiction | 5.1 | Data Not Collected; no analytics SDKs |
| Installing into shared paths | 2.4.5(ii) | Never `pip install` from the app |

## Packaging checklist (MAS)

- [x] `./Scripts/build_app.sh --mas` succeeded for build 8 (Mach-O onedir engine `0.2.0rc12`, `RunSpecimenEngine/_internal`, no `Helpers/lib/`). Do not upload a rebuild while build 8 is waiting.
- [x] Helper entitlements: `codesign -d --entitlements - …/RunSpecimenEngine/runspecimen` shows sandbox+inherit
- [x] App Sandbox entitlements (`RunSpecimen.mas.entitlements`)
- [x] `PrivacyInfo.xcprivacy` present
- [x] `AppIcon.icns` in `Contents/Resources`
- [x] `RSDistributionChannel=mas`
- [x] No `get-task-allow`
- [x] `./Scripts/archive_mas.sh` + `assert_archive_signing.sh` succeed (ad-hoc when no certs)
- [x] `./Scripts/test_mas_sandbox_e2e.sh` (actual APPROVE prompt + still waiting; never types APPROVE)
- [x] Store export fail-closed (`assert_store_export_ready.sh` + `test_store_export_gate.sh` negatives)
- [x] Apple Distribution signing + **local** Store pkg export (see asc-kit evidence) — Connect **replace/upload** still Yahor
- [x] Connect upload of **0.1.4 (9)** — recorded `WAITING_FOR_REVIEW` (submission `f0bb3ab1-…`, package `584f6868…`). **0.1.3 (8)** was rejected. Do not upload another build from automation.
- [x] Privacy policy URL in-app (Connect field **pending** Yahor)
- [ ] Screenshots uploaded into Connect Media — **pending Yahor** (local PNGs ready in [asc-kit/screenshots/](asc-kit/screenshots/))
- [x] Reviewer demo notes paste-ready ([asc-kit/reviewer-demo.md](asc-kit/reviewer-demo.md))
- [ ] Codex QA + Yahor release decision **before** Submit for Review

## Remaining Yahor-only blockers

1. **Leave** the recorded App Store Connect submission **0.1.4 (9)** alone. Automation will not withdraw it or upload a replacement.
2. Product site pins public GitHub + PyPI `0.2.0rc14`. The Mac App Store package recorded as in review is **0.1.4 (9)** with engine `0.2.0rc14` and does not include evidence expansion.
   Add an `apps.apple.com` link only when Apple returns a working URL.
3. Screenshots / privacy URL already pasted in Connect: confirm; do not Submit
   a second time from scripts.

Do **not** merge/publish/submit from agent automation without Yahor’s release decision.
Do **not** use Developer ID notarization as a Mac App Store validation stand-in.
Do **not** pass `-allowProvisioningUpdates` without explicit authorization.
