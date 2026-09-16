# Release checklist (Yahor) — MAS first

Short operator path for shipping the macOS companion. Detail:
[APP_STORE.md](APP_STORE.md), [docs/SECURITY_BOUNDARY.md](docs/SECURITY_BOUNDARY.md),
[Helpers/README.md](Helpers/README.md), [NOTARIZATION.md](NOTARIZATION.md).

**Invariants:** no telemetry; Approve never auto-types `APPROVE`; receipts ≠
digital signatures; payload is **not** OS-sandboxed by the UI sandbox alone.

**Do not** Submit for Review until Codex QA + your release decision.

## Yahor-only prerequisites

| Need | Check |
| --- | --- |
| Full **Xcode.app** (not CLT-only) | `xcodebuild -version` shows Xcode; `/Applications/Xcode.app` exists |
| Apple Developer Program | Active membership |
| **Apple Distribution** identity | `security find-identity -v -p codesigning` lists Apple Distribution |
| Mac App Store provisioning profile | For `com.darashkevich.runspecimen` |
| ASC API key or Apple ID + app password | Local `Config/signing.env` (never commit) |
| PyInstaller on the freeze machine | `python3 -c 'import PyInstaller'` |

This agent Mac: CLT only, **0 signing identities** — Archive/upload blocked here.

---

## A. Local smoke (no Apple cert) — CI equivalent

```bash
cd apps/macos
./Scripts/smoke_macos.sh
```

Covers: version gate, icons, security boundary, `--from-src` Prefer Bundled,
optional freeze, and **`--mas` fail-closed / frozen helper** when PyInstaller exists.

Manual GUI (optional): open `build/RunSpecimen.app`, Prefer Bundled Helper, doctor /
status, Approve sheet (type `APPROVE` yourself), quit → dashboard gone.

---

## B. MAS packaging (primary) — still unsigned until Xcode

```bash
cd apps/macos
python3 -m pip install --user 'pyinstaller>=6'
./Scripts/verify_app_icon.sh
./Scripts/test_security_boundary.sh
./Scripts/build_app.sh --mas
# Expect:
build/RunSpecimen.app/Contents/Helpers/runspecimen --version   # Mach-O
test ! -d build/RunSpecimen.app/Contents/Helpers/lib
/usr/libexec/PlistBuddy -c 'Print :RSDistributionChannel' \
  build/RunSpecimen.app/Contents/Info.plist   # → mas
test -f build/RunSpecimen.app/Contents/Resources/AppIcon.icns
```

`--mas` **fails closed** if freeze is impossible (no host-Python fallback).

---

## C. Archive + upload to App Store Connect (needs Xcode + certs)

1. `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`
2. Open project:
   ```bash
   ./Scripts/open_xcode.sh
   # or: open Package.swift in Xcode; ensure Resources/AppIcon.icns + MAS entitlements
   ```
3. Signing & Capabilities: Team, App Sandbox, `Entitlements/RunSpecimen.mas.entitlements`.
4. Scheme **RunSpecimen** → Product → **Archive**.
5. Distribute App → **App Store Connect** → Upload  
   (or `xcodebuild` + `Config/ExportOptions.mas.plist`).
6. ASC: version `0.1.3` / build `4` (bump as needed), screenshots, privacy URL,
   paste Review notes from APP_STORE.md.
7. **Stop before Submit for Review** until Codex QA + your decision.

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
| `./Scripts/build_app.sh --mas` frozen helper fail-closed | Done when PyInstaller present |
| PrivacyInfo + MAS entitlements | Done |
| Full Xcode Archive / ASC upload | **Blocked** — operator Xcode + Apple Distribution |
| Submit for Review | **Blocked** — Yahor release decision after Codex QA |
