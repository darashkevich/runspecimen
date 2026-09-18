# Release identity (do not ship the rc11 draft)

This file is the operator contract for the next public Python/plugin cut.
It does **not** authorize merge, GitHub Release publish, PyPI upload, or
App Store Connect changes.

## What is live today

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.10`** (published) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.10 |
| PyPI | **`0.2.0rc10`** | https://pypi.org/project/runspecimen/0.2.0rc10/ |
| Product site | rc10 install + “not yet public” Store language | do not retarget until GitHub **and** PyPI match a new version |
| Mac App Store | **not public** | Connect macOS **0.1.3 (5)** is `WAITING_FOR_REVIEW` — no `apps.apple.com` URL |

rc10 GitHub Release bytes and PyPI bytes were produced by **separate rebuilds**.
Do not treat those SHA-256 values as identical. Do **not** retag or republish
rc10 to “fix” that split.

| Artifact | GitHub Release SHA-256 | PyPI SHA-256 |
| --- | --- | --- |
| `runspecimen-0.2.0rc10-py3-none-any.whl` | `d82d04cc…` (release assets) | `26dd3aafd34da609f5cad36ace839188ef1e104b604a5dd1873171db081f88d7` |
| `runspecimen-0.2.0rc10.tar.gz` | `086bd860…` (release assets) | `369950aad9620a34906a919b4c2886b5c7d23853ef9e6a0014bd8b881f5d3469` |

The next published candidate must use **one validated wheel + sdist** as
identical bytes on GitHub and PyPI (`publish-pypi.yml` downloads release
assets; it does not rebuild).

## Do not publish `v0.2.0-rc.11`

| Fact | Value |
| --- | --- |
| Draft GitHub Release | https://github.com/darashkevich/runspecimen/releases/tag/untagged-784a2101f44640f11122 |
| Annotated tag | `v0.2.0-rc.11` → `29ece2f` |
| Peeled commit | **`ecc1709`** (`Align MAS E2E helper version gate with rc11.`) |
| PR #15 tip (later) | packaging, AppIcon catalog, window clamp, PyPI download-not-rebuild |

PR #15 changes the source archive and the PyPI workflow after `ecc1709`.
Publishing the existing draft would ship the wrong tree. **Do not move that
tag.** Leave the draft unpublished until a replacement is tagged from the
**merged, green** commit.

## Next public candidate: `0.2.0rc12`

| Field | Value |
| --- | --- |
| PEP 440 | `0.2.0rc12` |
| Git tag (create only after merge + green CI) | `v0.2.0-rc.12` (annotated, immutable) |
| Plugin / marketplace manifests | `0.2.0-rc.12` |
| Provenance | **checksum-only** (`SHA256SUMS`). `gh attestation verify` 404 means this candidate does **not** claim SLSA / GitHub Artifact Attestations |
| Mac marketing version | `0.1.3` |
| Next Connect upload | **build 6** (`CFBundleVersion`). Build **5** is already in review — do not reuse it |

Operator sequence (Yahor):

1. Merge the green PR to `main` (human decision; agents do not merge).
2. Confirm `git rev-parse HEAD` is the merged green commit.
3. `python3 scripts/release_check.py --output-dir /tmp/rs-rc12` (or CI-equivalent).
4. Create annotated tag `v0.2.0-rc.12` on **that** commit. Never retarget.
5. Attach **those same** wheel, sdist, plugin zip, and `SHA256SUMS` to a new
   GitHub Release. Do not attach a rebuilt second set.
6. Publish the GitHub Release (triggers OIDC PyPI of the downloaded bytes).
7. Verify tag, filenames, and SHA-256 on GitHub **and** PyPI before any
   website retarget.

## Website / Store language

Until step 7 is proven, keep rc10 install commands and “Mac App Store not yet
public” copy. Add an `apps.apple.com` link only when Apple returns a working
public URL.
