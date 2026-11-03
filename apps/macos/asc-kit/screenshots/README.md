# RunSpecimen 0.1.6 (16) — Mac App Store screenshots

Captured **2026-11-03** from the real running **MAS/Store-channel** app. These five PNGs replace the prior local-channel set. Each is **2880 × 1800 (16:10), RGB, sRGB IEC61966-2.1, with no alpha**, verified with `sips` and PNG IHDR inspection.

| File | What it shows | Dimensions |
| --- | --- | --- |
| [01-main.png](01-main.png) | Store main console, bundled engine, fresh demo lifecycle, clear lease and receipt inspector. No browser-dashboard action. | 2880 × 1800 |
| [02-doctor.png](02-doctor.png) | Doctor OK / Python 3.12.15, clear lease, and native status JSON with no approval, certificate or execution. There is no separate Doctor window. | 2880 × 1800 |
| [03-approve.png](03-approve.png) | Real human-approval PTY sheet with the confirmation field EMPTY. The review transcript is scrolled to the bound command and limits, keeping the OS account name out of the image. Nothing was typed or sent; the PTY was cancelled after capture. | 2880 × 1800 |
| [04-dashboard.png](04-dashboard.png) | Store-native read-only evidence view after Refresh read-only, showing config inspection and stored status. The filename is retained as requested; this is the native receipt/evidence inspector, not a browser dashboard. | 2880 × 1800 |
| [05-settings.png](05-settings.png) | MAS settings: bundled frozen engine, Prefer Bundled Helper and privacy. No host-CLI picker, host-Python fallback or installation section. | 2880 × 1800 |

## Store-channel verification

- Source at build time: `18f509ececa92c7a41faea35a42926241e84f53b`.
- Verified built Info.plist: `RSDistributionChannel=mas`, version **0.1.6**, build **16**.
- Built on 2026-11-02 with `Scripts/build_app.sh --mas`, `RS_SIGN_IDENTITY=-` and the repository's real MAS entitlements.
- Frozen bundled Mach-O helper **0.2.0rc16** under `Contents/Resources/RunSpecimenEngine/`; no source-tree/host-Python helper fallback. The private CPython 3.12.15 runtime was built with `Scripts/build_mas_python.sh` and excludes the unused disk-space APIs.
- App and helper signatures: **ad-hoc**, `TeamIdentifier=not set`. Both use App Sandbox; the helper inherits the sandbox. Deep/strict signature verification passed again after capture.
- Store restrictions were checked in the running UI: no browser Dashboard action; no Select runspecimen or Install guidance controls in Settings. The MAS app uses native evidence views and does not start a dashboard server.
- Required-reason API scan: no undeclared categories. Build, scan, dimensions and capture proofs: [archive/mas-build-evidence-2026-11-02/](archive/mas-build-evidence-2026-11-02/).

## Capture method

Used the already-built `/tmp/rs-asc-mas-20261102/RunSpecimen.app` and clean `/tmp/runspecimen-store-demo-016` workspace, created with `runspecimen init-demo`. The app was operated normally through its workspace/contract pickers. No approval or workload ran.

Actual native window/sheet images were captured through the computer-use window capture API. The prior `screencapture -l` attempt could not capture this session's window; no capture permissions or system settings were changed. Title bars/capture indicators and outer cursor pixels were cropped, then the captures were centered on neutral `#11161F`, with an outer rounded mask removing white backing outside the window. Main/status/evidence and Settings retain their captured pixel scale; the approval sheet is enlarged 1.5×. CoreGraphics converts/flattens the canvas to opaque sRGB. Product text and state were not retouched. All five final images were visually checked.

Raw captures and the framing script remain at `/tmp/rs-asc-mas-20261102/`. The framing script is also retained with the build evidence. The temporary app was quit after capture.

## Differences from an installed Store artifact

The visible controls and feature gating are the real MAS configuration. This local capture uses an **ad-hoc signature**, not distribution signing or a Store receipt. Its temporary screenshot-only bundle identifier (`com.darashkevich.runspecimen.screenshots.mas20261102`) isolates preferences/container data; app/helper code, MAS channel, version and sandbox entitlements are unchanged. The helper's installation path and the clean demo workspace path point under `/tmp` instead of an installed `/Applications` app and a reviewer's chosen workspace. A clean Store first launch normally opens its bundled Reviewer Demo; these images show the separately opened `init-demo` workspace. No personal home paths or notifications appear in the final images.

## Validation

```sh
sips -g pixelWidth -g pixelHeight -g space -g profile -g hasAlpha \
  01-main.png 02-doctor.png 03-approve.png 04-dashboard.png 05-settings.png
```

Every file reports `pixelWidth: 2880`, `pixelHeight: 1800`, `space: RGB`, `profile: sRGB IEC61966-2.1`, `hasAlpha: no`. PNG color type is 2 (RGB), 8 bits/channel. SHA-256 hashes are in [capture-verification-2026-11-03.json](archive/mas-build-evidence-2026-11-02/capture-verification-2026-11-03.json).

## Archive and boundaries

The four older October PNGs and `0.1.5-11/` are under `archive/`, byte-for-byte unchanged. The superseded November local-channel set and its README are under `archive/2026-11-02-local-channel/`. Only the five current submission images sit at the top level.

No distribution signing, provisioning/device changes, keychain changes, approval input, commits, pushes or uploads were performed.
