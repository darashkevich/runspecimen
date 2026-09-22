# Release identity

Python/plugin cut currently public: **`0.2.0rc13`** / **`v0.2.0-rc.13`**.
This file records what shipped; it does not authorize App Store Connect changes.

## What is live today

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.13`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.13 · tag peels to `3601934c850dd0405590a392ccd4c052cd7a16e4` |
| PyPI | **`0.2.0rc13`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc13/ |
| Homebrew tap | **`0.2.0rc13`** (same sdist URL + sha256) | https://github.com/darashkevich/homebrew-runspecimen · `brew tap darashkevich/runspecimen && brew install runspecimen` |
| Product site | `python3 -m pip install runspecimen==0.2.0rc13` | https://runspecimen.darashkevich.com/ |
| Mac App Store | **not public** | Connect macOS **0.1.3 (8)** is `WAITING_FOR_REVIEW` (submission `9c19e1cd-ebd1-4705-b683-5a5fdc2671f6`, submitted 2026-09-21T05:36:49Z). That binary froze engine **0.2.0rc12**. Builds 5 and 6 were rejected and cancelled. |

Install pin is required: pip will not select an RC without `==0.2.0rc13`.

### rc13 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc13-py3-none-any.whl` | `ad096b7bd3fe2ce79f2bc1102d07a08898b8d631172b7b5375459ddc17633269` |
| `runspecimen-0.2.0rc13.tar.gz` | `0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5` |
| `runspecimen-plugin-0.2.0-rc.13.zip` | `02463625ce907ebf064448a944640088fe3ef77ee72088eaa831dab28cf99214` (GitHub only) |

`publish-pypi.yml` downloaded those GitHub assets and uploaded the wheel and sdist without rebuilding. Provenance is **checksum-only**: no SLSA attestation on the wheel.

## Previous public cut

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.12`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.12 · tag peels to `eb23483bfa7c4e2ac62a3802fa2feb5d87f53cdd` |
| PyPI | **`0.2.0rc12`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc12/ |
| Product site at publication | pinned `runspecimen==0.2.0rc12` | https://runspecimen.darashkevich.com/ now pins rc13 |
| Mac App Store | **not public** | Connect macOS **0.1.3 (8)** is `WAITING_FOR_REVIEW` (submission `9c19e1cd-ebd1-4705-b683-5a5fdc2671f6`, submitted 2026-09-21T05:36:49Z). Builds 5 and 6 were rejected and cancelled. |

Install pin is required: pip will not select an RC without `==0.2.0rc12`.

### rc12 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc12-py3-none-any.whl` | `4ad914698f3856693349274d235a079ecb562e7f6be63e619c616da4cb1d0939` |
| `runspecimen-0.2.0rc12.tar.gz` | `bf1f1a6223a1f65504a13f98bb1ddbad773dffd458bb6b5dcf32920c43c8bfed` |
| `runspecimen-plugin-0.2.0-rc.12.zip` | `1d1b27e4e99baf5fbcd27aa20e162c416d47d6ec26ecc28e7a81a285782db4c1` (GitHub only) |

`publish-pypi.yml` downloaded those GitHub assets and uploaded the wheel/sdist without rebuilding. Provenance is **checksum-only**: `gh attestation verify` returns HTTP 404 (no GitHub SLSA attestation on the wheel).

## Do not publish `v0.2.0-rc.11`

Draft https://github.com/darashkevich/runspecimen/releases/tag/untagged-784a2101f44640f11122 still peels to **`ecc1709`**. Leave it unpublished. Do not move that tag.

## Historical: rc10 digest split

rc10 GitHub Release bytes and PyPI bytes were produced by **separate rebuilds**. Do not retag or republish rc10.

## Website / Store language

Product page install commands match **rc13**. Add an `apps.apple.com` link only when Apple returns a working public URL. The binary in review is **0.1.3 (8)** with engine **0.2.0rc12**. Do not upload another build while that submission is `WAITING_FOR_REVIEW`.
