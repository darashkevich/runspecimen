# RunSpecimen product demo

A standalone, everyday explainer of the core RunSpecimen story: a looping
real-CLI clip, four short onboarding GIFs, then a simulated walkthrough
(review a run plan, type `APPROVE` yourself, watch one run, inspect a receipt —
and a refused check if the result was altered). Copy is written for a
non-technical reader: review the plan, type APPROVE yourself, keep the receipt.
Exact engine terms sit behind “Show details”.

This folder is **additive marketing content**. It is not shipped in the Python
package, does not talk to the CLI, and does not approve or execute anything.

## Preview

Open the page in a browser. No build step, no install, no network. Serve the
parent `web/` directory so the onboarding GIFs (sibling `onboarding/assets/`)
resolve:

```bash
python3 -m http.server 8765 --directory web
# then visit http://127.0.0.1:8765/product-demo/
```

`open web/product-demo/index.html` also works for `file://` because the GIFs
are referenced as `../onboarding/assets/…`.

Files:

| File | Role |
| --- | --- |
| `index.html` | Page structure and copy |
| `styles.css` | Layout, color, responsive and dark styles |
| `app.js` | Simulated review → approve → run → verify flow |
| `favicon.svg` | Local icon |
| `../onboarding/assets/*.gif` | Hero loop + four-step CLI clips (see that folder's README to rebuild) |

## Embed on a product page

Host this folder as static files, then iframe it. The `embed=1` query hides the
site header and extra footer links so the block sits more quietly in a parent
page:

```html
<iframe
  src="https://example.com/product-demo/index.html?embed=1"
  title="RunSpecimen: you approve what may run, then keep the receipt"
  style="width:100%;min-height:2400px;border:0;"
  loading="lazy"
></iframe>
```

Host this folder **together with** `web/onboarding/assets/` (sibling paths).
`index.html` loads `styles.css`, `app.js`, and `favicon.svg` as relative paths,
and the GIFs as `../onboarding/assets/…`. There are no CDN or font-network
dependencies.

Suggested iframe height is a starting point — the hero clip, four-step row,
and walkthrough grow on small screens. Prefer a tall frame or let the parent
page link to the full page.

To regenerate the GIFs: `python3 web/onboarding/build_gifs.py` (needs Pillow).

## Accuracy notes

Copy is grounded in the repository docs (`docs/ABOUT.md`, `docs/FAQ.md`,
`docs/USER_GUIDE.md`, `docs/MARKETING_PITCHES.md`) and the sample contract in
`examples/demo_contract.json`. The looping GIFs are **real CLI output** from
`init-demo` (see `web/onboarding/`). The interactive piece is a **simulation**:

- Approval in the walkthrough is pedagogical. Real approval is an interactive
  TTY `runspecimen approve` step; agents cannot type `APPROVE`.
- Walkthrough hashes and the certificate are labeled demo-only. Live `verify`
  re-hashes files on disk. The GIF clips use hashes from the captured demo run.
- The page does not claim sandboxing, biometric admission, phone signing,
  installed-holder execution, or app-store features.
