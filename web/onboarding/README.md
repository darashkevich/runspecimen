# RunSpecimen onboarding GIFs

Short animated clips of the core lifecycle for a product/marketing page:
review a bounded contract, type `APPROVE` at a TTY, run once, then verify
the certified receipt.

This folder is **additive marketing content**. It is not shipped in the Python
package, does not talk to a live CLI in the browser, and does not approve or
execute anything. It mirrors `web/product-demo/` (PR #57): static files plus a
rebuild script.

## Preview

```bash
python3 -m http.server 8766 --directory web/onboarding
# http://127.0.0.1:8766/
```

Or open `web/onboarding/index.html` directly.

| File | Role |
| --- | --- |
| `index.html` | Gallery + embed snippet (`?embed=1` hides chrome) |
| `styles.css` | Layout; same light tokens as the product demo |
| `build_gifs.py` | Regenerates the GIFs from `transcripts/session.json` |
| `transcripts/session.json` | Frozen real-CLI capture (`init-demo` via PTY) |
| `assets/*.gif` | Committed clips + `manifest.json` (sizes) |

## Rebuild

The renderer needs Pillow. It does **not** need a TTY if the transcript is
already present:

```bash
python3 -m pip install pillow
python3 web/onboarding/build_gifs.py
```

That writes:

- `assets/00-full-lifecycle.gif` — four completed beats, one loop
- `assets/01-review-contract.gif` — `runspecimen approve` contract summary
- `assets/02-type-approve.gif` — type `APPROVE`, then the approval JSON
- `assets/03-run-execute.gif` — `preflight` then `run`
- `assets/04-verify-receipt.gif` — `postflight` then `verify`
- `assets/manifest.json` — width, height, frame count, bytes

Recapture a live session (requires `runspecimen` on `PATH`) and rebuild:

```bash
python3 web/onboarding/build_gifs.py --capture
```

`--capture` creates a fresh `init-demo` workspace, drives `approve` through a
PTY (the human phrase is entered only in that throwaway demo), then records
`preflight` / `run` / `postflight` / `verify` JSON. Absolute workspace paths
are rewritten to `$WORKSPACE` so the GIFs show the documented
`--workspace . --contract contract.json` form.

## Embed on the product page

Host `web/onboarding/assets/` as static files. Suggested hero:

```html
<img
  src="/onboarding/assets/00-full-lifecycle.gif"
  width="960"
  height="600"
  alt="RunSpecimen: review the contract, type APPROVE, run once, verify the receipt."
>
```

Four-step row (same dimensions each):

```html
<img src="/onboarding/assets/01-review-contract.gif" width="960" height="600" alt="Review the bounded contract.">
<img src="/onboarding/assets/02-type-approve.gif" width="960" height="600" alt="Type APPROVE at a real TTY.">
<img src="/onboarding/assets/03-run-execute.gif" width="960" height="600" alt="One bounded run completes.">
<img src="/onboarding/assets/04-verify-receipt.gif" width="960" height="600" alt="Verify the certified receipt.">
```

Optional gallery iframe:

```html
<iframe
  src="https://example.com/onboarding/index.html?embed=1"
  title="RunSpecimen onboarding clips"
  style="width:100%;min-height:720px;border:0;"
  loading="lazy"
></iframe>
```

Keep `width` / `height` attributes so layout does not jump. After the
committed rebuild, the five GIFs total about **505 KiB** (see
`assets/manifest.json`).

## Accuracy

- Commands and JSON match the installed CLI (`indent=2`, `sort_keys=True`).
- The approve prompt is the real TTY text from `runspecimen.approve`
  (campaign, argv, sources, outputs, timeout, isolation claim, hashes, TTL).
- Isolation is shown as the product prints it: default backend `none`, not an
  OS sandbox.
- Hashes, timestamps, and `certificate_id` come from the captured demo run.
  Recapturing on another machine will change those bytes (interpreter path,
  source hash, clock). Pixel-identical rebuilds use the committed transcript.
- Clips abridge only by scrolling a viewport; they do not invent fields or
  guarantees.
