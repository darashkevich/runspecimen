# macOS presentation previews

Static HTML stand-ins for the B2C SwiftUI prototype. They exist because this
change cannot render SwiftUI on Linux CI. They follow
[B2C_DESIGN_DIRECTION.md](../B2C_DESIGN_DIRECTION.md) and are **not** the
enforcement boundary.

| File | Screen |
| --- | --- |
| `welcome.html` | First-launch onboarding |
| `review-approve.html` | Review and approve (PTY still visible; APPROVE is not typed) |
| `running.html` | Running now |
| `all-good.html` | Success receipt |
| `something-changed.html` | Drift / mismatch result |

PNG captures of those pages (1280×800 window chrome) sit beside the HTML:

`welcome.png`, `review-approve.png`, `running.png`, `all-good.png`,
`something-changed.png`.

Open any file in a browser, or:

```bash
python3 -m http.server 8766 --directory docs/ux/previews
```
