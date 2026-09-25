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
