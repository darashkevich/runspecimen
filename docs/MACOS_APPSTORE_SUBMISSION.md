# Mac App Store submission — human-only steps

This file is the ordered checklist for uploading **0.1.6 (16)** with bundled
engine **0.2.0rc16**. It does not upload, sign with a Distribution identity,
create profiles, accept agreements, or submit for review.

In-repo packaging: [apps/macos/APP_STORE.md](../apps/macos/APP_STORE.md),
[apps/macos/RELEASE_CHECKLIST.md](../apps/macos/RELEASE_CHECKLIST.md),
[apps/macos/asc-kit/metadata.md](../apps/macos/asc-kit/metadata.md).
Never pass `-allowProvisioningUpdates`.

## What this tree already has

| Item | Status on this branch |
| --- | --- |
| Marketing version / build | **0.1.6 (16)** in `project.yml`, `Info-mas.plist`, `Resources/Info.plist`, ASC metadata |
| Bundled engine gate | freeze / `--mas` must match `src/runspecimen/__version__` = **0.2.0rc16** |
| App Sandbox + Hardened Runtime | `Entitlements/RunSpecimen.mas.entitlements`; `ENABLE_HARDENED_RUNTIME=YES` |
| Helper inherit sandbox | `Entitlements/RunSpecimen.helper.entitlements` (sandbox + inherit + PyInstaller JIT exceptions) |
| Privacy manifest | `Resources/PrivacyInfo.xcprivacy` (`NSPrivacyTracking=false`, empty collected types, UserDefaults `CA92.1`, SystemBootTime `35F9.1`, FileTimestamp `C617.1` + `3B52.1`) |
| Export compliance key | `ITSAppUsesNonExemptEncryption=false` in `Config/Info-mas.plist` |
| ASC paste copy | `apps/macos/asc-kit/metadata.md` (description, What's New, keywords, support/privacy URLs) |
| CI unsigned Release archive | `apps/macos/Scripts/archive_unsigned_release.sh` from `smoke_macos.sh` (ad-hoc `CODE_SIGN_IDENTITY=-` only) |

There is no `fastlane/` folder. Connect fields are pasted from `asc-kit/metadata.md`.

## Blockers (do not skip)

1. **EU trader status.** Connect macOS **historical 0.1.4 (9)** is `Removed from App Store` because EU trader status is missing. A new upload does not clear that legal requirement.
2. **Yahor's Apple Distribution identity** and the **RunSpecimen MAS** provisioning profile must already exist on the signing Mac. This repository must not create, download, or regenerate certificates, profiles, or devices.
3. **App Store Connect access** (Apple ID or API key) lives only on Yahor's machine. Do not store keys in git.
4. **In-repo screenshots are older builds** (About shot still shows `0.1.3 (4)` / `0.2.0rc10`; other PNGs predate 0.1.6). Recapture 1280×800 media from a 0.1.6 (16) / rc16 archive before Connect upload.
5. **Product site still pinned rc15** on 2026-11-01. Source is `darashkevich/darashkevich.com` `sites/runspecimen/`, not this repo. Support and privacy URLs must stay live.
6. **Yahor release decision / independent QA closure** before Submit for Review. This file does not authorize review.
7. CI produces an **unsigned / ad-hoc** archive only. It is not the upload binary.

## Ordered human steps

Do these on Yahor's Mac. Stop if any step needs a new certificate, profile, device, or agreement.

### 1. Confirm identities already in the login keychain

```bash
security find-identity -v -p codesigning
security find-identity -v | grep 'Mac Developer Installer'
```

You need **Apple Distribution** (Application) and **3rd Party Mac Developer Installer**.
If either is missing, stop. Install them from the Apple Developer portal yourself.
Do not pass `-allowProvisioningUpdates`.

Confirm the existing Mac App Store profile `RunSpecimen MAS` for
`UN6KF8636A.com.darashkevich.runspecimen` is already on disk
(`~/Library/Developer/Xcode/UserData/Provisioning Profiles/`).
Do not create or regenerate it from this repo.

### 2. Freeze the rc16 helper with the private MAS Python

A stock Homebrew/setup-python runtime imports DiskSpace APIs and is refused.
Use the already-documented private CPython 3.12.15 prefix if it exists:

```bash
"$HOME/.venvs/mas-python312/bin/python3.12" -m pip install 'pyinstaller>=6'
cd apps/macos
RS_FREEZE_PYTHON="$HOME/.venvs/mas-python312/bin/python3.12" \
  ./Scripts/freeze_helper.sh --enable --require --verify
Helpers/payload/runspecimen --version   # must contain 0.2.0rc16
```

### 3. Archive and sign in Xcode with the existing identity

Either:

```bash
cd apps/macos
./Scripts/archive_mas.sh
```

or open the committed project and use the existing team:

```bash
cd apps/macos
./Scripts/open_xcode.sh
# Signing & Capabilities: Team UN6KF8636A, App Sandbox, MAS entitlements
# Product → Archive (Release, Any Mac / generic macOS)
```

Do not enable "Automatically manage signing" updates that would call
`-allowProvisioningUpdates`. Do not register devices.

### 4. Export a local Store package (no upload yet)

```bash
cd apps/macos
RS_ARCHIVE_PATH="$PWD/build/RunSpecimen.xcarchive" \
RS_EXPORT_DIR="$PWD/build/export" \
RS_EXPORT_DESTINATION=export ./Scripts/export_mas.sh
```

`export` writes a `.pkg` only. It does not upload and does not submit for review.
Confirm `assert_store_export_ready.sh` passed (Apple Distribution + matching
team + MAS profile + Distribution-signed archive).

### 5. Upload the signed package

Only after Yahor authorizes a release:

```bash
RS_ARCHIVE_PATH="$PWD/build/RunSpecimen.xcarchive" \
RS_EXPORT_DIR="$PWD/build/export" \
RS_EXPORT_DESTINATION=upload ./Scripts/export_mas.sh
```

or Xcode Organizer → Distribute App → App Store Connect → Upload.
Do not use Transporter with a newly generated profile.
Do not upload from CI. Do not upload the unsigned archive.

### 6. App Store Connect version record

Create or reopen macOS version **0.1.6**. Paste from
[apps/macos/asc-kit/metadata.md](../apps/macos/asc-kit/metadata.md):

| Field | Value |
| --- | --- |
| Name | RunSpecimen |
| Subtitle | Local evidence control surface |
| Category | Developer Tools |
| Description | (full text in metadata.md) |
| What's New | (0.1.6 / rc16 text in metadata.md) |
| Keywords | runspecimen,evidence,approval,local,cli,developer,receipt,preflight,control |
| Support URL | https://runspecimen.darashkevich.com/support/ |
| Privacy Policy URL | https://runspecimen.darashkevich.com/privacy/ |
| Marketing URL | https://runspecimen.darashkevich.com/ |
| Copyright | Copyright © 2026 Yahor Darashkevich. Apache-2.0. |
| Build | select the uploaded **16** binary after processing |

Confirm the selected build's engine is **0.2.0rc16** before attaching it.

### 7. Export compliance

Answer **No** to non-exempt encryption. The Info.plist key
`ITSAppUsesNonExemptEncryption` is already `false`. The app uses HTTPS only for
optional in-browser docs links. Do not invent a custom encryption declaration.

### 8. Privacy nutrition labels

Declare **Data Not Collected** while that remains true (no analytics, crash
uploaders, ads, accounts, or phone-home). Align Connect with
`Resources/PrivacyInfo.xcprivacy`:

- Tracking: no
- Collected data types: none
- Required-reason APIs already declared in the manifest: UserDefaults
  (`CA92.1` bookmarks / last workspace), SystemBootTime (`35F9.1`),
  FileTimestamp (`C617.1`, `3B52.1`)

### 9. Screenshots

Upload new 1280×800 (or current ASC sizes) captures from the **0.1.6 (16)**
archive, not the older PNGs under `apps/macos/asc-kit/screenshots/`:

1. Main Console with brand + Bundled Helpers + status (not Terminal.app)
2. Approve sheet with empty PTY input (never type `APPROVE` for the shot)
3. Settings → Privacy (Telemetry None — local only)
4. About with the privacy-policy link and **0.1.6 (16)** / **0.2.0rc16**

Recipe: [apps/macos/asc-kit/screenshots/README.md](../apps/macos/asc-kit/screenshots/README.md).

### 10. Review notes, then stop

Paste [apps/macos/asc-kit/reviewer-demo.md](../apps/macos/asc-kit/reviewer-demo.md).
Do **not** Submit for Review until Yahor closes the remaining QA / trader-status
blockers. This document ends at upload + Connect fields.

## What CI already proved

`macos-app` runs `smoke_macos.sh`, which freezes the MAS helper and then
`archive_unsigned_release.sh`: Release configuration, ad-hoc
`CODE_SIGN_IDENTITY=-`, no profiles, no `-allowProvisioningUpdates`.
That archive is structural smoke. Replace it with step 3 before upload.
