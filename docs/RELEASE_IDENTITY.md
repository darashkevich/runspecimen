# Release identity

Python/plugin cut currently public: **`0.2.0rc16`** / **`v0.2.0-rc.16`**.
This file records what shipped; it does not authorize App Store Connect changes.

Candidate source on this branch identifies as **`0.2.0rc16`** / **`0.2.0-rc.16`**. That cut is published (tag `v0.2.0-rc.16` on `ae94701`). Advisory [GHSA-8357-m9wf-gjh9](https://github.com/darashkevich/runspecimen/security/advisories/GHSA-8357-m9wf-gjh9). The live Homebrew tap and the product site still served rc15 on 2026-11-01.

App Store Connect macOS **0.1.4 (9)** was queried on 2026-09-28 as `Removed from App Store` (EU trader status missing) and `downloadable=true` (build `51a18894-02e3-4846-86f5-29cc345567f0`, review item `APPROVED`). That release is unchanged. The current preparation target is **0.1.6 (16)**: Yahor authorized merging PR #75 on 2026-10-18 and confirmed Mac 0.1.5 withdrawn from review. This records preparation only; shipping is blocked until independent QA findings are closed.

## What is live today

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.16`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.16 |
| PyPI | **`0.2.0rc16`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc16/ |
| Homebrew tap | **`0.2.0rc15`** (tap still lagged 2026-11-01) | https://github.com/darashkevich/homebrew-runspecimen · `brew tap darashkevich/runspecimen && brew install runspecimen` |
| Product site | still `python3 -m pip install --pre runspecimen==0.2.0rc15` (lagged 2026-11-01) | https://runspecimen.darashkevich.com/ — source is `darashkevich/darashkevich.com` `sites/runspecimen/`, not this repo |
| Mac App Store | **Removed from App Store** (EU trader status missing) | Connect macOS **0.1.4 (9)** is public with engine **0.2.0rc14**. Builds 5–8 were rejected or superseded. |

Install pin is required: `pip install --pre runspecimen==0.2.0rc16`. pip will not select an RC without `--pre` or an exact `==` pin.

### rc16 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc16-py3-none-any.whl` | `59044b56fbe3fa798a5ebb8ead3f0460141c96c98e8d0861aafd4a83ede8e9cc` |
| `runspecimen-0.2.0rc16.tar.gz` | `83625441d316816107087870525a88d20cd42b61c69e7e398ce95cdcc3fe31d4` |
| `runspecimen-plugin-0.2.0-rc.16.zip` | `1d5961b9c70b18efacb7ebf6babcdb6a51825f2a786d559b8a980677cc67c2bd` (GitHub only) |

`publish-pypi.yml` downloaded those GitHub assets and uploaded the wheel and sdist without rebuilding. Provenance is **checksum-only**: no SLSA attestation on the wheel.

## Previous public cut

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.15`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.15 |
| PyPI | **`0.2.0rc15`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc15/ |
| Homebrew tap / product site at publication | still pinned `0.2.0rc15` on 2026-11-01 | tap and `https://runspecimen.darashkevich.com/` lagged the rc16 publish |
| Mac App Store | **Removed from App Store** (EU trader status missing) | Connect macOS **0.1.4 (9)** is public with engine **0.2.0rc14**. Builds 5–8 were rejected or superseded. |

Install pin is required: pip will not select an RC without `==0.2.0rc15`.

### rc15 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `d9d0c9dfc978beb29ac34901d788e647812d3f663c703281da35d2172ac4f048` |
| `runspecimen-0.2.0rc15.tar.gz` | `7abe59f54e974140e305f3b31f24767ca078eaafe0b606c26f606cb1ece9e63b` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (GitHub only) |

`publish-pypi.yml` downloaded those GitHub assets and uploaded the wheel and sdist without rebuilding. Provenance is **checksum-only**: no SLSA attestation on the wheel.

## Previous public cut

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.14`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.14 · tag peels to `25f4013c5c84b89b24024182f7c308dcffe084b4` |
| PyPI | **`0.2.0rc14`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc14/ |
| Product site at publication | pinned `runspecimen==0.2.0rc14` | https://runspecimen.darashkevich.com/ now pins rc15 after site update |
| Mac App Store | **Removed from App Store** (EU trader status missing) | Connect macOS **0.1.4 (9)** with engine **0.2.0rc14** |

Install pin is required: pip will not select an RC without `==0.2.0rc14`.

### rc14 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc14-py3-none-any.whl` | `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948` |
| `runspecimen-0.2.0rc14.tar.gz` | `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3` |
| `runspecimen-plugin-0.2.0-rc.14.zip` | `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` (GitHub only) |

`publish-pypi.yml` downloaded those GitHub assets and uploaded the wheel and sdist without rebuilding. Provenance is **checksum-only**: no SLSA attestation on the wheel.

## Previous public cut

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.13`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.13 · tag peels to `3601934c850dd0405590a392ccd4c052cd7a16e4` |
| PyPI | **`0.2.0rc13`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc13/ |
| Product site at publication | pinned `runspecimen==0.2.0rc13` | https://runspecimen.darashkevich.com/ now pins rc14 after site update |
| Mac App Store | **not public** | Historical: **0.1.3 (8)** was submitted 2026-09-21 and later rejected. It is not the package in review. |

Install pin is required: pip will not select an RC without `==0.2.0rc13`.

### rc13 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc13-py3-none-any.whl` | `ad096b7bd3fe2ce79f2bc1102d07a08898b8d631172b7b5375459ddc17633269` |
| `runspecimen-0.2.0rc13.tar.gz` | `0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5` |
| `runspecimen-plugin-0.2.0-rc.13.zip` | `02463625ce907ebf064448a944640088fe3ef77ee72088eaa831dab28cf99214` (GitHub only) |

## Do not publish `v0.2.0-rc.11`

Draft https://github.com/darashkevich/runspecimen/releases/tag/untagged-784a2101f44640f11122 still peels to **`ecc1709`**. Leave it unpublished. Do not move that tag. Do not move `v0.2.0-rc.12` or `v0.2.0-rc.13`.

## Historical: rc10 digest split

rc10 GitHub Release bytes and PyPI bytes were produced by **separate rebuilds**. Do not retag or republish rc10.

## Website / Store language

Product page install commands still matched **rc15** on 2026-11-01 (site source is not in this repo). Mac App Store **0.1.4 (9)** with engine **0.2.0rc14** is **Removed from App Store** (EU trader status missing in App Store Connect).
