# RunSpecimen onboarding GIFs

Short animated clips of the core lifecycle, generated from a captured
`runspecimen init-demo` session: review a bounded contract, type `APPROVE`
at a TTY, run once, then verify the certified receipt.

The clips are **embedded on the product demo page**
(`web/product-demo/index.html`). This folder holds the assets and the
rebuild script only — there is no standalone landing page.

This folder is **additive marketing content**. It is not shipped in the Python
package, does not talk to a live CLI in the browser, and does not approve or
execute anything.

## Files

| File | Role |
| --- | --- |
| `build_gifs.py` | Regenerates the GIFs from `transcripts/session.json` |
| `transcripts/session.json` | Frozen real-CLI capture (`init-demo` via PTY) |
| `assets/*.gif` | Clips the product demo embeds + `manifest.json` (sizes) |

## Rebuild

The renderer needs Pillow. It does **not** need a TTY if the transcript is
already present:

```bash
python3 -m pip install pillow
python3 web/onboarding/build_gifs.py
```

That writes:

- `assets/00-full-lifecycle.gif` — four completed beats, one loop (product-demo hero)
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

After the committed rebuild, the five GIFs total about **505 KiB**.

## Where they appear

`web/product-demo/index.html` loads them as sibling paths:

```
../onboarding/assets/00-full-lifecycle.gif   (hero)
../onboarding/assets/01-review-contract.gif  (four-step row)
../onboarding/assets/02-type-approve.gif
../onboarding/assets/03-run-execute.gif
../onboarding/assets/04-verify-receipt.gif
```

Host `web/product-demo/` and `web/onboarding/assets/` together (for example
serve the `web/` directory). See `web/product-demo/README.md` for preview and
embed notes.

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
