# APP_STORE.md — Mac App Store & notarization compliance

Checklist and review posture for the RunSpecimen macOS app
(`apps/macos`). Consult current Apple docs before each submission:

- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) (esp. **2.4.5**, **2.5.1**, **4.2**, **5.1**)
- [App Sandbox](https://developer.apple.com/documentation/security/app_sandbox)
- [Accessing files from the macOS App Sandbox](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox)
- [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)
- [Privacy manifest files](https://developer.apple.com/documentation/bundleresources/privacy_manifest_files)
- [Notarizing macOS software](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)

## Recommendation (v1)

| Channel | Role | Verdict |
| --- | --- | --- |
| **Target B — Developer ID + notarization** | Primary ship for v1 | **Recommended now** |
| **Target A — Mac App Store** | Stretch / follow-on | Architecture ready; submit after review-risk mitigation |

### Why Developer ID first

1. **Guideline 2.4.5(i)** — MAS requires App Sandbox. The enforcement engine is an
   external Python CLI. Sandbox-compatible access needs
   `NSOpenPanel` + security-scoped bookmarks +
   `com.apple.security.files.user-selected.executable`.
2. **Guideline 2.4.5(viii)** — MAS apps “may not use deprecated or optionally installed
   technologies (e.g. Java).” A hard dependency on a user-installed PyPI tool is a
   realistic rejection risk unless the binary is user-selected *and* review notes explain
   the security boundary clearly — or the engine is embedded.
3. **Guideline 2.4.5(ii)** — Self-contained single-app bundle; cannot install code into
   shared locations. We must not `pip install` into system/user site-packages from the app.
4. **Guideline 4.2** — Minimum functionality. The app is a substantial native control
   surface (status, evidence, lifecycle gating), not a web clipping — but reviewers may
   still question “wrapper around CLI” framing. Copy and screenshots must lead with
   native UX, not Terminal.

Store stretch plan: embed a signed `runspecimen` helper (Python runtime + package, or a
future compiled helper) under `Contents/Helpers` with `com.apple.security.inherit`, then
re-submit Target A.

## Entitlements

### Target A — Mac App Store (`Entitlements/RunSpecimen.mas.entitlements`)

| Entitlement | Purpose |
| --- | --- |
| `com.apple.security.app-sandbox` | Required for MAS (2.4.5(i)) |
| `com.apple.security.files.user-selected.read-write` | Workspace + evidence via Open panel |
| `com.apple.security.files.user-selected.executable` | Execute user-picked `runspecimen` binary |
| `com.apple.security.network.client` | Optional docs links (GitHub) opened in browser; no telemetry |
| `com.apple.security.network.server` | Only if launching loopback `dashboard` from the app |

Do **not** enable: camera, mic, contacts, location, Apple Events automation (unless
Terminal handoff requires it — prefer `open`/`NSWorkspace` with a `.command` file the
user double-clicks, or in-app PTY).

### Target B — Developer ID (`Entitlements/RunSpecimen.developer-id.entitlements`)

- Same sandbox entitlements preferred for parity and safer defaults.
- Hardened Runtime **required** for notarization — enable at codesign time with
  `--options runtime` (see `Scripts/sign_and_notarize.sh` and `NOTARIZATION.md`).
  It is not a boolean key inside the entitlements plist.
- Avoid Hardened Runtime *exception* entitlements (`allow-unsigned-executable-memory`,
  `disable-library-validation`, etc.) unless a future embedded interpreter forces them —
  document any exception in this file before enabling.
- Never ship `get-task-allow` in release entitlements.

## Privacy

### App Privacy (App Store Connect) / nutrition labels

Declare **Data Not Collected** while the following remain true:

- No analytics, crash reporters that upload PII, advertising, or accounts
- No phone-home; local-only product invariant
- Docs links open in the system browser; the app does not scrape or transmit workspace contents

Update this declaration immediately if any SDK or network call is added.

### In-app privacy policy

MAS requires a privacy policy URL in metadata **and** an in-app accessible link
(guideline 5.1.1). Ship Settings → Privacy with a link to the published policy
(runspecimen site or GitHub `SECURITY.md` / privacy page).

### `PrivacyInfo.xcprivacy`

Ship `Resources/PrivacyInfo.xcprivacy`:

- `NSPrivacyTracking` = false
- `NSPrivacyCollectedDataTypes` = []
- Required-reason APIs: declare only what the binary actually uses
  (commonly `UserDefaults` → `CA92.1` for app preferences such as bookmark blobs /
  last workspace). Audit with each Xcode SDK bump.

## Review notes (draft for App Review)

> RunSpecimen is a local safety/evidence control surface for one human-approved bounded
> run at a time. The Mac app is a native SwiftUI shell; enforcement remains the
> user-selected `runspecimen` CLI (Apache-2.0). Approval requires an interactive PTY
> and the human typing APPROVE — the app does not auto-approve and has no agent API.
> The optional dashboard is loopback-only and read-only. No telemetry. Workspace and
> CLI paths are granted via NSOpenPanel security-scoped bookmarks.

Demo path for reviewers:

1. Install `runspecimen` via PyPI (or provide a notarized helper build in Notes).
2. Open the app → Choose CLI → Choose workspace (`examples/showcase`).
3. Refresh status / inspect certificate (read-only).
4. Show Approve sheet prompts for human `APPROVE` on a PTY (do not automate).

## Rejection risks & mitigations

| Risk | Guideline | Mitigation |
| --- | --- | --- |
| “Requires optionally installed Python/CLI” | 2.4.5(viii) | User-selected executable + install guidance; long-term embed helper |
| “Thin wrapper / minimal functionality” | 4.2 | Lead with native status/evidence UX; not a WKWebView of the dashboard |
| Executing arbitrary user binaries | Sandbox / safety | Restrict to basename `runspecimen` + `--version` probe; show hash/path |
| Misleading security claims | 2.3 / honesty | Copy states: not an OS sandbox; receipts ≠ digital signatures |
| Background dashboard after quit | 2.4.5(iii) | Kill dashboard child on terminate; never launch agents at login |
| Private APIs | 2.5.1 | Public AppKit/SwiftUI/Foundation/Darwin PTY only |
| Telemetry contradiction | 5.1 | Keep Data Not Collected honest; no analytics SDKs |
| Installing tools into shared paths | 2.4.5(ii) | Never `pip install` from the app; link to docs only |

## Packaging checklist

- [ ] Built with Xcode (MAS packaging requirement 2.4.5(ii))
- [ ] App Sandbox enabled (Target A)
- [ ] Hardened Runtime enabled via `codesign --options runtime` (Target B)
- [ ] `PrivacyInfo.xcprivacy` present and audited
- [ ] App Privacy answers = Data Not Collected (while true)
- [ ] Privacy policy URL in Connect + in-app
- [ ] No `get-task-allow` in release
- [ ] Notarize (`notarytool`) + staple for direct download — see **[NOTARIZATION.md](NOTARIZATION.md)**
- [ ] Screenshots show native UI, honest non-goals
- [ ] Export compliance / encryption: HTTPS docs links only → standard answers
- [ ] Dashboard child terminated on app quit (implemented in `CLIService.stopDashboard`)

## Remaining blockers (engineering)

- Developer ID Application certificate + Apple Team ID (operator keychain — not in-repo).
- Notarization credentials (App Store Connect API key) — operator-held secrets in
  `Config/signing.env` (gitignored). Run `./Scripts/check_signing_identity.sh`.
- Full Xcode recommended for Archive / Organizer / MAS upload (CLT builds via `build_app.sh`).
- Optional: embed signed engine helper for clean Target A — scaffold in `Helpers/` + ADR-002.

