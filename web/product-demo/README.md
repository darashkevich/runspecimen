# RunSpecimen product demo

A standalone, non-technical explainer and simulated walkthrough of the core
RunSpecimen story: review a bounded contract, type `APPROVE`, watch one run,
then inspect a checkable receipt (and a refused check if the output was altered).

This folder is **additive marketing content**. It is not shipped in the Python
package, does not talk to the CLI, and does not approve or execute anything.

## Preview

Open the page in a browser. No build step, no install, no network:

```bash
# from this folder, or from the repo root
open web/product-demo/index.html
```

Or serve it locally (useful if your browser restricts `file://` scripts):

```bash
python3 -m http.server 8765 --directory web/product-demo
# then visit http://127.0.0.1:8765/
```

Files:

| File | Role |
| --- | --- |
| `index.html` | Page structure and copy |
| `styles.css` | Layout, color, responsive and dark styles |
| `app.js` | Simulated review → approve → run → verify flow |
| `favicon.svg` | Local icon |

## Embed on a product page

Host this folder as static files, then iframe it. The `embed=1` query hides the
site header and extra footer links so the block sits more quietly in a parent
page:

```html
<iframe
  src="https://example.com/product-demo/index.html?embed=1"
  title="RunSpecimen: approve a run, then prove what ran"
  style="width:100%;min-height:1100px;border:0;"
  loading="lazy"
></iframe>
```

You can also copy the four files into any static host or CMS. Keep them
together; `index.html` loads `styles.css`, `app.js`, and `favicon.svg` as
relative paths. There are no CDN or font-network dependencies.

Suggested iframe height is a starting point — the walkthrough grows on small
screens. Prefer a tall frame or let the parent page link to the full page.

## Accuracy notes

Copy is grounded in the repository docs (`docs/ABOUT.md`, `docs/FAQ.md`,
`docs/USER_GUIDE.md`, `docs/MARKETING_PITCHES.md`) and the sample contract in
`examples/demo_contract.json`. The interactive piece is a **simulation**:

- Approval on this page is pedagogical. Real approval is an interactive TTY
  `runspecimen approve` step; agents cannot type `APPROVE`.
- Hashes and the certificate are labeled demo-only. Live `verify` re-hashes
  files on disk.
- The page does not claim sandboxing, biometric admission, phone signing,
  installed-holder execution, or app-store features.
