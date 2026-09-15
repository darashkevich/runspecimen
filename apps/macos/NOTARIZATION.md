# Developer ID notarization — Target B ship path

Primary v1 distribution for the RunSpecimen macOS app. Mac App Store (Target A)
remains a stretch; see [APP_STORE.md](APP_STORE.md).

**This machine may have no signing identity.** Scripts under `Scripts/` fail with
setup instructions when certs or notary credentials are missing. Do not commit
secrets; use `Config/signing.env` (gitignored) copied from the example.

## Prerequisites

| Item | How to obtain |
| --- | --- |
| Apple Developer Program membership | [developer.apple.com](https://developer.apple.com) |
| **Developer ID Application** certificate | Xcode → Settings → Accounts → Manage Certificates, or Certificates, Identifiers & Profiles |
| Team ID | Membership details in the Apple Developer portal |
| Notary credentials | App Store Connect → Users and Access → Integrations → **Team Keys** (Issuer ID + Key ID + `.p8`), **or** an Apple ID app-specific password for `notarytool` |
| Full **Xcode.app** (recommended) | Archive / Organizer; CLT can compile via `Scripts/build_app.sh` but Archive UI needs Xcode |
| Hardened Runtime | Enabled at codesign time (`--options runtime`) — required for notarization |

Check local readiness:

```bash
cd apps/macos
./Scripts/check_signing_identity.sh
```

Expected when ready: one line containing `Developer ID Application: …`.
When not ready: non-zero exit and install steps (current status on many build hosts).

## Exact ship sequence (CLI)

### 1. Build the `.app`

```bash
cd apps/macos
./Scripts/build_app.sh
# → build/RunSpecimen.app (ad-hoc signed for local smoke)
```

For a distribution build, re-sign with Developer ID (next step) rather than shipping
the ad-hoc signature.

### 2. Codesign with Developer ID + Hardened Runtime

```bash
# Optional: copy and fill Config/signing.env (see Config/signing.env.example)
set -a && source Config/signing.env && set +a

./Scripts/sign_and_notarize.sh sign
```

What the script does:

1. Resolves `RS_SIGN_IDENTITY` (or the first `Developer ID Application` identity).
2. Runs `codesign --force --deep --options runtime --timestamp \
     --entitlements Entitlements/RunSpecimen.developer-id.entitlements \
     --sign "$IDENTITY" build/RunSpecimen.app`.
3. Verifies with `codesign --verify --deep --strict` and prints
   `codesign -dv --verbose=2` (confirm **Runtime=Hardened** / flags include runtime).

Entitlements stay sandbox-aligned with MAS (see `APP_STORE.md`). Do **not** add
Hardened Runtime *exception* entitlements (`allow-unsigned-executable-memory`,
`disable-library-validation`, etc.) unless an embedded helper forces them — document
any exception in `APP_STORE.md` first.

### 3. Notarize

```bash
./Scripts/sign_and_notarize.sh notarize
```

Submits a zip of the app via `xcrun notarytool submit … --wait`, using either:

- `RS_NOTARY_KEY` / `RS_NOTARY_KEY_ID` / `RS_NOTARY_ISSUER` (API key — preferred), or
- `RS_NOTARY_APPLE_ID` / `RS_NOTARY_PASSWORD` / `RS_NOTARY_TEAM_ID` (app-specific password).

On success, Apple stores a notarization ticket for the binary’s CDHash.

### 4. Staple

```bash
./Scripts/sign_and_notarize.sh staple
# equivalent: xcrun stapler staple build/RunSpecimen.app
```

Stapling embeds the ticket so Gatekeeper works offline.

### 5. Distribute

```bash
./Scripts/sign_and_notarize.sh package
# → build/RunSpecimen-macos.zip (ditto -c -k --keepParent)
```

Ship that zip (GitHub Release, site download, etc.). Users should see a normal
Gatekeeper open — not “unidentified developer” — after notarization + staple.

One-shot (sign → notarize → staple → package):

```bash
./Scripts/sign_and_notarize.sh all
```

## Exact ship sequence (Xcode Archive UI)

1. Open the package in Xcode (`xed Package.swift` or generate an Xcode project).
2. Select the RunSpecimen scheme → **Product → Archive**.
3. Organizer → select archive → **Distribute App** → **Developer ID** → Upload / Export.
4. Ensure the archive uses `Entitlements/RunSpecimen.developer-id.entitlements` and
   Hardened Runtime is enabled on the target.
5. After Apple finishes notarization (Organizer or email), staple if you exported a
   local copy: `xcrun stapler staple /path/to/RunSpecimen.app`.
6. Zip with `ditto -c -k --keepParent RunSpecimen.app RunSpecimen-macos.zip`.

## Verification (operator)

```bash
spctl --assess --type execute -vv build/RunSpecimen.app
codesign --verify --deep --strict --verbose=2 build/RunSpecimen.app
xcrun stapler validate build/RunSpecimen.app
```

Expect `spctl` to report accepted / source = Notarized Developer ID (wording varies by OS).

## What this repo does *not* store

- Private keys, `.p8` files, app-specific passwords, or provisioning profiles
- A checked-in `Config/signing.env` (only `signing.env.example`)

## Current blocker (typical agent / CI Mac)

If `security find-identity -v -p codesigning` prints `0 valid identities found`, you
cannot complete steps 2–5 here. Local smoke remains:

```bash
./Scripts/build_app.sh && open build/RunSpecimen.app
# or non-GUI: ./Scripts/smoke_macos.sh
```

Obtain a Developer ID Application certificate on the release Mac, then re-run
`./Scripts/sign_and_notarize.sh all`.

When a helper is staged (`Helpers/payload/runspecimen`), `build_app.sh` copies it into
`Contents/Helpers/`. Sign that child with `Entitlements/RunSpecimen.helper.entitlements`
(same Team ID) before notarizing the whole bundle — see `Scripts/stage_helper.sh`.
