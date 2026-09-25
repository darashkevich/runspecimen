# Release checklist (Yahor) — MAS first

Short operator path for shipping the macOS companion. Detail:
[APP_STORE.md](APP_STORE.md), [docs/SECURITY_BOUNDARY.md](docs/SECURITY_BOUNDARY.md),
[Helpers/README.md](Helpers/README.md), [NOTARIZATION.md](NOTARIZATION.md).

**Invariants:** no telemetry; Approve never auto-types `APPROVE`; receipts ≠
digital signatures; payload is **not** OS-sandboxed by the UI sandbox alone.

**Engine:** a future MAS freeze must match `src/runspecimen/__version__` (**`0.2.0rc14`**). The submitted **0.1.4 (9)** froze that engine without evidence expansion. Successor source here is **0.1.5 (10)** and is not uploaded.

**Do not** upload or Submit another Mac App Store build while **0.1.4 (9)** is the recorded submission.

## Yahor-only prerequisites

| Need | Check |
| --- | --- |
| Full **Xcode.app** | ✅ Xcode 27.0 on this Mac (`xcodebuild -version`) |
| Apple Developer Program | Active membership |
| **Apple Distribution** identity | `security find-identity -v -p codesigning` lists Apple Distribution |
| Mac App Store provisioning profile | For `com.darashkevich.runspecimen` |
| ASC API key or Apple ID + app password | Local `Config/signing.env` (never commit) |
| PyInstaller on the freeze machine | `python3 -c 'import PyInstaller'` |

This agent Mac: Xcode 27 ready; **0 Apple signing identities** — ad-hoc Archive works;
ASC upload still blocked until Distribution cert + Team.

---

## A. Local smoke (no Apple cert) — CI equivalent

```bash
cd apps/macos
./Scripts/smoke_macos.sh
```

Covers: version gate, icons, security boundary, `--from-src` Prefer Bundled,
optional freeze, and **`--mas` fail-closed / frozen helper == repo version** when
PyInstaller exists.

Manual GUI (optional): open `build/RunSpecimen.app`, Prefer Bundled Helper, doctor /
status, Approve sheet (type `APPROVE` yourself), quit → dashboard gone.

---

## B. MAS packaging (primary)

```bash
cd apps/macos
python3 -m pip install --user 'pyinstaller>=6'
./Scripts/verify_app_icon.sh
./Scripts/test_security_boundary.sh
./Scripts/build_app.sh --mas
# Expect:
build/RunSpecimen.app/Contents/Helpers/runspecimen --version   # → 0.2.0rc14 on a new freeze; build 8 is 0.2.0rc12
test ! -d build/RunSpecimen.app/Contents/Helpers/lib
/usr/libexec/PlistBuddy -c 'Print :RSDistributionChannel' \
  build/RunSpecimen.app/Contents/Info.plist   # → mas
test -f build/RunSpecimen.app/Contents/Resources/AppIcon.icns
```

`--mas` **fails closed** if freeze is impossible (no host-Python fallback).

---

## C. Archive + upload to App Store Connect

1. Freeze + structural Archive (ad-hoc OK without certs):
   ```bash
   ./Scripts/archive_mas.sh
   # → apps/macos/build/RunSpecimen.xcarchive
   ```
2. For ASC upload, open project and set Team:
   ```bash
   ./Scripts/open_xcode.sh
   # Signing & Capabilities: Team + Apple Distribution + MAS entitlements
   # Product → Archive → Distribute App → App Store Connect → Upload
   ```
   Or `RS_EXPORT_DESTINATION=export ./Scripts/export_mas.sh` (local Store pkg;
   UUID + installer cert; no upload). Default destination still `upload`.
3. ASC: **0.1.4 (9)** is the package recorded as `WAITING_FOR_REVIEW`. Do not upload another build or Submit again from this checklist. Successor source is **0.1.5 (10)** and is not an upload.

Optional: `brew install xcodegen` then `./Scripts/generate_xcodeproj.sh` if
`project.yml` changed (committed `RunSpecimen.xcodeproj` is the default Archive input).

---

## D. Developer ID notarization (secondary)

Only if you also want a direct-download build. Not required for MAS.

```bash
./Scripts/check_signing_identity.sh
cp Config/signing.env.example Config/signing.env   # fill secrets locally
./Scripts/build_app.sh --frozen-helper             # or --mas then re-stamp channel
./Scripts/sign_and_notarize.sh all
```

See NOTARIZATION.md.

---

## Current status (honest)

| Item | Status |
| --- | --- |
| Ad-hoc `.app` + Prefer Bundled (`--from-src`) | Works (local/CI) |
| App icon wired (`AppIcon.icns` / iconset / 1024) | Done |
| Security boundary docs + tests | Done |
| `./Scripts/build_app.sh --mas` frozen helper fail-closed | Done; must report **rc10** |
| PrivacyInfo + MAS entitlements | Done |
| `RunSpecimen.xcodeproj` + `archive_mas.sh` | Done (Xcode 27; nested helper sandbox+inherit) |
| Nested helper signing (`sign_nested_helper.sh`) | Done — identity-aware; ad-hoc only when no certs |
| Sandboxed e2e (`test_mas_sandbox_e2e.sh`) | Done — requires actual APPROVE prompt + still waiting (never types APPROVE) |
| Store export fail-closed (`assert_store_export_ready.sh`) | Done — requires `RS_ARCHIVE_APP` (app+helper); exact profile fields; Developer ID/ad-hoc refused before export; negatives in `test_store_export_gate.sh` |
| ASC kit (`asc-kit/`) | Metadata + reviewer demo ready; 4 real ad-hoc MAS screenshots captured (Connect upload still Yahor) |
| ASC upload / Submit for Review | **Blocked** — Apple Distribution + Yahor decision after Codex QA |
