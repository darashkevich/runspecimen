# Screenshots (ASC)

**Status: PENDING** — no App Store Connect screenshot PNGs are committed in this repo.

Capture on a Retina Mac, dark UI as shipped, **native** Main Console (not Terminal.app).

## Required shots (check when captured)

- [ ] **PENDING** Main Console — brand + status + evidence (1280×800 or current ASC Mac size)
- [ ] **PENDING** Approve sheet — PTY visible, empty input (do not show typed APPROVE if possible)
- [ ] **PENDING** Settings / Privacy — privacy policy link visible
- [ ] **PENDING** Optional: About sheet with version `0.1.3` / engine note

## Capture tips

1. Build MAS app: `./Scripts/build_app.sh --mas` or use Archive app.
2. Open workspace `examples/showcase`.
3. Prefer Bundled Helper.
4. Use system screenshot → crop to ASC size; opaque product chrome, no Desktop clutter.
5. Store locally (not in git) or in ASC Media Manager only — avoid committing large binaries unless Yahor asks.

## Icon for Connect

Use `../Resources/AppIcon-1024.png` (opaque `#070A0F` field, **not** pre-rounded). Verified by `./Scripts/verify_app_icon.sh`.
