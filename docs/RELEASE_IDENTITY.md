# Release identity

Python/plugin cut on this commit: **`0.2.0rc14`** / **`v0.2.0-rc.14`**.
Checksums for that release are the GitHub Release `SHA256SUMS` asset (checksum-only, not SLSA-attested).
The table below is the previous public cut. This file does not authorize App Store Connect changes.

## Previous public cut (still the bytes on PyPI until `0.2.0rc14` is published)

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.13`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.13 · tag peels to `3601934c850dd0405590a392ccd4c052cd7a16e4` |
| PyPI | **`0.2.0rc13`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc13/ |
| Homebrew tap | **`0.2.0rc13`** (same sdist URL + sha256) | https://github.com/darashkevich/homebrew-runspecimen · `brew tap darashkevich/runspecimen && brew install runspecimen` |
| Product site | `python3 -m pip install runspecimen==0.2.0rc13` | https://runspecimen.darashkevich.com/ |
| Mac App Store | **not public** | Connect macOS **0.1.3 (8)** is `IN_REVIEW` / was `WAITING_FOR_REVIEW` (submission `9c19e1cd-ebd1-4705-b683-5a5fdc2671f6`, submitted 2026-09-21T05:36:49Z). That binary froze engine **0.2.0rc12**. Builds 5 and 6 were rejected and cancelled. |

Install pin is required: pip will not select an RC without `==0.2.0rc13`.

### rc13 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc13-py3-none-any.whl` | `ad096b7bd3fe2ce79f2bc1102d07a08898b8d631172b7b5375459ddc17633269` |
| `runspecimen-0.2.0rc13.tar.gz` | `0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5` |
| `runspecimen-plugin-0.2.0-rc.13.zip` | `02463625ce907ebf064448a944640088fe3ef77ee72088eaa831dab28cf99214` (GitHub only) |

`publish-pypi.yml` downloaded those GitHub assets and uploaded the wheel and sdist without rebuilding. Provenance is **checksum-only**: no SLSA attestation on the wheel.

## Do not publish `v0.2.0-rc.11`

Draft https://github.com/darashkevich/runspecimen/releases/tag/untagged-784a2101f44640f11122 still peels to **`ecc1709`**. Leave it unpublished. Do not move that tag. Do not move `v0.2.0-rc.12` or `v0.2.0-rc.13`.

## Historical: rc10 digest split

rc10 GitHub Release bytes and PyPI bytes were produced by **separate rebuilds**. Do not retag or republish rc10.

## Website / Store language

Product page install commands still match **rc13** until rc14 is published and the site pin is updated. Add an `apps.apple.com` link only when Apple returns a working public URL. The binary in review is **0.1.3 (8)** with engine **0.2.0rc12**. Do not upload another build while that submission is in review.
