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
| **Target A — Mac App Store** | **Primary** | `./Scripts/build_app.sh --mas` (frozen **0.2.0rc10** helper) → `./Scripts/archive_mas.sh` / Xcode Archive → App Store Connect |
| **Target B — Developer ID + notarization** | Secondary / direct download | Optional after MAS; same sandbox entitlements preferred |

### Why MAS-first now

1. **Guideline 2.4.5(viii)** — Store builds embed a **frozen Mach-O** helper
   (`Contents/Resources/RunSpecimenEngine/`, PyInstaller **onedir** + `_internal/`)
   built from the current engine (`0.2.0rc10` on this branch). **Onefile is not used**
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
# Confirm helper is current engine (rc10 on this branch):
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
(replace `TEAMID` before export). **Fail-closed export:**
`./Scripts/assert_store_export_ready.sh` then `./Scripts/export_mas.sh` —
Apple Distribution + matching team + MAS profile required; **Developer ID is not
sufficient**.

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
| `com.apple.security.network.server` | Loopback `dashboard` only |

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
| Build | `4` (bump per upload) |
| Min macOS | 14.0 |
| Bundled engine | `0.2.0rc10` (must match `src/runspecimen/__version__`) |
| Icon | `Resources/AppIcon.icns` (+ iconset / 1024 for Connect) |

## Review notes (paste into App Review)

> RunSpecimen is a local safety/evidence control surface for one human-approved
> bounded run at a time. The Mac app is a sandboxed SwiftUI shell. Enforcement is
> the **bundled** `Contents/Helpers/runspecimen` CLI (Apache-2.0, frozen Mach-O —
> no host Python). Approval requires an interactive PTY and the human typing
> APPROVE — the app never auto-approves and has no agent API. App Sandbox
> confines the UI (+ inherit helper); it does **not** claim to OS-sandbox the
> payload under test. Certificates are hash-chained receipts, not asymmetric
> digital signatures. The optional dashboard is loopback-only and read-only.
> No telemetry. Workspace paths use NSOpenPanel security-scoped bookmarks.

### Demo path for reviewers

1. Launch RunSpecimen (bundled helper resolves automatically — Source = “Bundled Helpers”).
2. Choose workspace → `examples/showcase` (or attach a sample workspace in Review notes).
3. Refresh status / inspect certificate (read-only).
4. Open Approve sheet — type `APPROVE` yourself on the PTY (do not automate).
5. Quit — confirm dashboard child is gone.

Provide a sample workspace zip in Review notes if the showcase tree is not in the build.

## Screenshots / metadata checklist

- [ ] 1280×800 (or current ASC sizes) showing Main Console with brand + status (not Terminal)
- [ ] Approve sheet visible (human PTY, no auto-fill)
- [ ] Settings / Privacy link visible
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

- [x] `./Scripts/build_app.sh --mas` succeeds (Mach-O onedir engine == repo `0.2.0rc10`, `RunSpecimenEngine/_internal`, no `Helpers/lib/`)
- [x] Helper entitlements: `codesign -d --entitlements - …/RunSpecimenEngine/runspecimen` shows sandbox+inherit
- [x] App Sandbox entitlements (`RunSpecimen.mas.entitlements`)
- [x] `PrivacyInfo.xcprivacy` present
- [x] `AppIcon.icns` in `Contents/Resources`
- [x] `RSDistributionChannel=mas`
- [x] No `get-task-allow`
- [x] `./Scripts/archive_mas.sh` + `assert_archive_signing.sh` succeed (ad-hoc when no certs)
- [x] `./Scripts/test_mas_sandbox_e2e.sh` (actual APPROVE prompt + still waiting; never types APPROVE)
- [x] Store export fail-closed (`assert_store_export_ready.sh` + `test_store_export_gate.sh` negatives)
- [ ] Apple Distribution signing + upload to App Store Connect (Yahor) — **pending**
- [x] Privacy policy URL in-app (Connect field **pending** Yahor)
- [ ] Screenshots in Connect — **pending** (see [asc-kit/screenshots/](asc-kit/screenshots/))
- [x] Reviewer demo notes paste-ready ([asc-kit/reviewer-demo.md](asc-kit/reviewer-demo.md))
- [ ] Codex QA + Yahor release decision **before** Submit for Review

## Remaining Yahor-only blockers

1. Create/download **Apple Distribution** cert + Mac App Store profile for
   `com.darashkevich.runspecimen`; set Team in Xcode (replace ad-hoc Archive).
2. Create ASC app + API key; fill `Config/signing.env` locally (gitignored); set
   `TEAMID` in `Config/ExportOptions.mas.plist`.
3. Archive → Upload → metadata → **Stop before Submit for Review** until Codex QA
   + your release decision.

Do **not** merge/publish/submit from agent automation without Yahor’s release decision.
