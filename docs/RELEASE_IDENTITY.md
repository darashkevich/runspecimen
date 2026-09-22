# Release identity

Python/plugin cut on this commit: **`0.2.0rc13`** / **`v0.2.0-rc.13`**.
Checksums for that release are the GitHub Release `SHA256SUMS` asset (checksum-only, not SLSA-attested).
The table below is the previous public cut. This file does not authorize App Store Connect changes.

## Previous public cut (still the bytes on PyPI until `0.2.0rc13` is published)

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.12`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.12 · tag peels to `eb23483bfa7c4e2ac62a3802fa2feb5d87f53cdd` |
| PyPI | **`0.2.0rc12`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc12/ |
| Product site | `python3 -m pip install runspecimen==0.2.0rc12` | https://runspecimen.darashkevich.com/ |
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

Product page install commands match **rc12**. Add an `apps.apple.com` link only when Apple returns a working public URL. The binary in review is **0.1.3 (8)**. Do not upload another build while that submission is `WAITING_FOR_REVIEW`.
