# Release checklist (Yahor)

Short operator path for shipping the macOS companion. Full detail lives in
[NOTARIZATION.md](NOTARIZATION.md), [APP_STORE.md](APP_STORE.md), and
[Helpers/README.md](Helpers/README.md).

**Invariants:** no telemetry; Approve never auto-types `APPROVE`; receipts ≠
digital signatures. Do not claim notarization or MAS readiness without a cert.

## A. Local smoke (no Apple cert)

```bash
cd apps/macos
./Scripts/smoke_macos.sh          # CI-equivalent; uses --from-src helper
./Scripts/build_app.sh --from-src # or plain build_app.sh after staging
open build/RunSpecimen.app
```

Manual GUI: pick workspace (`examples/showcase`), Prefer Bundled Helper, doctor /
status / validate, Approve sheet (type `APPROVE` yourself), quit → dashboard gone.

## B. Optional frozen helper (still no cert)

Self-contained Mach-O under `Contents/Helpers/` — better MAS posture later; still
**unsigned / local-only** until Developer ID.

### End-to-end (`RS_FREEZE_HELPER=1`)

```bash
cd apps/macos
python3 -m pip install --user 'pyinstaller>=6'   # local only; not a repo dep
RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh --verify
./Scripts/build_app.sh
# Confirm frozen helper in the bundle (Mach-O; no lib/ package tree):
build/RunSpecimen.app/Contents/Helpers/runspecimen --version
test ! -d build/RunSpecimen.app/Contents/Helpers/lib
open build/RunSpecimen.app
# Engine → Prefer Bundled Helper → Source = “Bundled Helpers”
```

Note: `./Scripts/smoke_macos.sh` always re-stages `--from-src` (CI default). Run it
before a freeze experiment, or re-freeze afterward — do not expect smoke to preserve
a frozen payload.
### One-shot via build_app

```bash
./Scripts/build_app.sh --frozen-helper
# Tries PyInstaller freeze; if missing/skipped → clear log + --from-src fallback
```

Without PyInstaller (CI default): freeze skips exit 0; `--frozen-helper` falls
back to `--from-src`. Default `build_app.sh` / smoke do **not** require PyInstaller.

Ad-hoc `build_app.sh` deep-signs the bundle; for a frozen Mach-O helper it then
clears the app-sandbox stamp on `Contents/Helpers/runspecimen` and reseals so
shell smoke (`--version`) works. `sign_and_notarize.sh` does proper inside-out
Developer ID signing (helper inherit entitlements → app).## C. Developer ID + notarize (blocked without cert)

1. **Apple Developer Program** membership active.
2. Install **Developer ID Application** cert  
   Xcode → Settings → Accounts → Manage Certificates → Developer ID Application  
   (or Certificates, Identifiers & Profiles).
3. Confirm identity:
   ```bash
   ./Scripts/check_signing_identity.sh
   # expect: Developer ID Application: …
   ```
4. Copy and fill secrets locally (never commit):
   ```bash
   cp Config/signing.env.example Config/signing.env
   # RS_SIGN_IDENTITY, RS_NOTARY_TEAM_ID,
   # plus API key (RS_NOTARY_KEY / KEY_ID / ISSUER) or Apple ID + app-specific password
   set -a && source Config/signing.env && set +a
   ```
5. Stage helper (from-src or freeze), build, then:
   ```bash
   ./Scripts/build_app.sh --from-src    # or --frozen-helper
   ./Scripts/sign_and_notarize.sh all   # sign → notarize → staple → zip
   ```
6. Verify:
   ```bash
   spctl --assess --type execute -vv build/RunSpecimen.app
   codesign --verify --deep --strict --verbose=2 build/RunSpecimen.app
   xcrun stapler validate build/RunSpecimen.app
   ```
7. Ship `build/RunSpecimen-macos.zip` (or wrap the stapled `.app` in a DMG with
   your usual tool — zip is what `sign_and_notarize.sh package` produces).

If step 2 is missing, scripts fail with setup steps. Ad-hoc local builds still work.

## D. Mac App Store stretch (after Target B)

- Sandbox + bookmarks + PrivacyInfo already in place.
- Prefer a **signed** bundled helper (`Contents/Helpers`, inherit entitlements).
- Freeze + CPython NOTICE audit recommended for 2.4.5(viii) posture.
- Archive in Xcode → Distribute → App Store Connect; see APP_STORE.md.

## Current status (honest)

| Item | Status |
| --- | --- |
| Ad-hoc `.app` + Prefer Bundled Helper (`--from-src`) | Works |
| Optional PyInstaller freeze (`RS_FREEZE_HELPER=1`) | Local when PyInstaller installed |
| Developer ID / notarize / staple | **Blocked** — 0 signing identities on typical agent Macs |
| MAS upload | Stretch after notarized Target B + helper story |
