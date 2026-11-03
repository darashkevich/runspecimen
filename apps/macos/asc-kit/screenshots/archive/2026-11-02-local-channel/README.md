# RunSpecimen 0.1.6 (16) screenshots

Captured locally on 2026-11-02 from main `18f509ececa92c7a41faea35a42926241e84f53b`.
The five new files below are real captures, centered on a neutral `#11161F` canvas.
Each is **2880 × 1800 pixels (16:10), RGB, sRGB IEC61966-2.1, no alpha**.

| File | What it shows |
| --- | --- |
| [01-main.png](01-main.png) | Main console: bundled helper, fresh demo contract, lifecycle, clear lease, receipt inspector. No run or approval recorded. |
| [02-doctor.png](02-doctor.png) | Native doctor/status view: Doctor OK, Python version, clear lease and the stored status JSON with `approval: null`, `phase: none` and no events. There is no separate Doctor window; this is the native console with the inspector scrolled to status. |
| [03-approve.png](03-approve.png) | Human approval sheet with live PTY, bound demo command and limits. The confirmation field is empty; nothing was sent. The transcript is scrolled to the contract review, keeping the OS account name out of view. The sheet was cancelled after capture. |
| [04-dashboard.png](04-dashboard.png) | Real loopback-only, read-only browser dashboard: ready-to-review demo, safety boundary and evidence trust ladder. This feature belongs to the local channel; see the Store caveat below. |
| [05-settings.png](05-settings.png) | Settings: bundled helper identity and version, Prefer Bundled Helper control, and local-only privacy information. |

## Build and capture provenance

- Built with `./apps/macos/Scripts/build_app.sh --from-src` at the source SHA above.
- App Info.plist verified as **0.1.6 (16)**; bundled engine reports **0.2.0rc16**.
- Local channel, source-tree helper; **ad-hoc only**, `Signature=adhoc`, `TeamIdentifier=not set`.
- A temporary copy at `/tmp/rs-asc-capture-20261102/RunSpecimen.app` uses an isolated screenshot bundle identifier, `com.darashkevich.runspecimen.screenshots20261102`, so the capture does not load or overwrite the normal app's saved workspace preferences. Product source code was not edited.
- Fresh workspace created by `runspecimen init-demo --workspace /tmp/runspecimen-demo-asc-016`. No contract execution, approval, key, keychain, trust or system-setting action was performed.
- `screencapture -l` could not obtain a window image in this session. Native app captures use the computer-use window capture instead. Title bars/capture indicators were cropped away; a small outer corner mask removes the capture's white backing outside the window. No product text or state was retouched.
- The dashboard is a real headless Chrome viewport capture from the running loopback server, using a fresh temporary browser profile. It was captured after its entry animation settled; the lower page is cropped below the trust ladder. Browser chrome and personal tabs are absent.
- Main/status retain their original pixel size; approval is enlarged 1.5×, while settings/dashboard are reduced proportionally to fit the canvas. Color conversion and flattening use CoreGraphics in sRGB.
- Build log, raw captures and framing script are retained locally under `/tmp/rs-asc-capture-20261102/`.
- Previous PNGs and the `0.1.5-11/` directory are unchanged. Nothing committed, pushed or uploaded.

## Mac App Store caveat

These are the **requested local ad-hoc build captures**, not screenshots of an exported Store artifact. `DistributionChannel.mas` disables the browser dashboard and host CLI selection/install controls. Consequently **04-dashboard.png must not be used to advertise the Store app's features**, and the local-only controls visible in 01, 02 and 05 also require Store-channel recapture before treating this as final submission media. No distribution signing or Store export was attempted. All five requested local views were captured successfully.

## Validation

Run for each of the five new PNGs:

```sh
sips -g pixelWidth -g pixelHeight -g space -g profile -g hasAlpha 01-main.png 02-doctor.png 03-approve.png 04-dashboard.png 05-settings.png
```

Verified for every file: `pixelWidth: 2880`, `pixelHeight: 1800`, `space: RGB`, `profile: sRGB IEC61966-2.1`, `hasAlpha: no`.

---

## Historical capture notes (retained)

# Screenshots (ASC)

The four PNGs in this directory predate the submitted **0.1.4 (9)** Store app. They are not the **0.1.5 (11)** candidate and they are not what Apple is reviewing.

Captures from the signed **0.1.5 (11)** archive app (source `3a0f483`, Apple Distribution, not the installed Store package) are in [0.1.5-11/](0.1.5-11/). Those are local evidence for the candidate. Do not upload them as the media for **0.1.4 (9)**.

**Status: CAPTURED (local ad-hoc MAS app)** — real product chrome from the sandboxed
`RunSpecimen.app` (Archive ad-hoc / `build/screenshot-RunSpecimen.app`), not mocks.

Capture host: Retina Mac. Logical window size **1280×800** → PNG pixels **2560×1600**
(2×). Dark UI as shipped. Native Main Console (not Terminal.app).

## Shots

| File | Content | ASC size note |
| --- | --- | --- |
| [01-main-console-1280x800.png](01-main-console-1280x800.png) | Main Console — brand, Bundled Helpers, lifecycle + evidence (`approval: null`) | 1280×800 @2× |
| [02-approve-sheet-pty-1280x800.png](02-approve-sheet-pty-1280x800.png) | Approve sheet — PTY live, empty input (“Type APPROVE… nothing is sent automatically”); never typed APPROVE | 1280×800 @2× |
| [03-settings-privacy.png](03-settings-privacy.png) | Settings — CLI engine + **Privacy: Telemetry None — local only** | Settings window (not full ASC canvas) |
| [04-about-privacy-links-1280x800.png](04-about-privacy-links-1280x800.png) | About — app `0.1.3 (4)` / engine `0.2.0rc10` + **Privacy policy** link visible | 1280×800 @2× |

Optional raw captures under [raw/](raw/) are local provenance only (may be gitignored).

## Honest caveats (not faked)

- Built/signed **ad-hoc** MAS channel app — not Apple Distribution / Store export.
- Workspace breadcrumb shows a sandbox e2e demo path under
  `~/Library/Containers/com.darashkevich.runspecimen/.../rs-mas-e2e-.../demo`
  (real bookmarked workspace from sandboxed runs). Yahor may re-capture with
  `examples/showcase` after a clean Open Workspace for prettier Connect media.
- Approve sheet JSON may show a draft `approved_at` timestamp in the preview
  document; the input stays empty and the invariant line states the app never
  types APPROVE.

## Capture recipe (reproduce)

1. `./Scripts/archive_mas.sh` (or reuse `/tmp/runspecimen-mas/.../RunSpecimen.app`).
2. `ditto` into `build/screenshot-RunSpecimen.app`, `xattr -cr`, `open` it.
3. Open workspace + `contract.json` (sandbox-accessible).
4. Resize window to 1280×800; `screencapture -x -R x,y,w,h …`.
5. Lifecycle → Approve… for PTY sheet (do **not** type APPROVE).
6. RunSpecimen → About / Settings for policy + privacy rows.

## Icon for Connect

Use `../Resources/AppIcon-1024.png` (opaque `#070A0F` field, **not** pre-rounded).
Verified by `./Scripts/verify_app_icon.sh`.
