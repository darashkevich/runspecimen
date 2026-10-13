# Release identity

Python/plugin cut currently public: **`0.2.0rc15`** / **`v0.2.0-rc.15`**.
This file records what shipped; it does not authorize App Store Connect changes.

## What is live today

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.15`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.15 |
| PyPI | **`0.2.0rc15`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc15/ |
| Homebrew tap | **`0.2.0rc15`** (same sdist URL + sha256) | https://github.com/darashkevich/homebrew-runspecimen · `brew tap darashkevich/runspecimen && brew install runspecimen` |
| Product site | `python3 -m pip install runspecimen==0.2.0rc15` | https://runspecimen.darashkevich.com/ (pin update may lag the package publish) |
| Mac App Store | **READY_FOR_SALE** | Connect macOS **0.1.4 (9)** is public with engine **0.2.0rc14**. Builds 5–8 were rejected or superseded. |

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
| Mac App Store | **READY_FOR_SALE** | Connect macOS **0.1.4 (9)** with engine **0.2.0rc14** |

Install pin is required: pip will not select an RC without `==0.2.0rc14`.

### rc14 identical bytes (checksum-only)

| Artifact | SHA-256 (GitHub Release = PyPI) |
| --- | --- |
| `runspecimen-0.2.0rc14-py3-none-any.whl` | `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948` |
| `runspecimen-0.2.0rc14.tar.gz` | `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3` |
| `runspecimen-plugin-0.2.0-rc.14.zip` | `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` (GitHub only) |

## Do not publish `v0.2.0-rc.11`

Draft https://github.com/darashkevich/runspecimen/releases/tag/untagged-784a2101f44640f11122 still peels to **`ecc1709`**. Leave it unpublished. Do not move that tag. Do not move `v0.2.0-rc.12` or `v0.2.0-rc.13`.

## Historical: rc10 digest split

rc10 GitHub Release bytes and PyPI bytes were produced by **separate rebuilds**. Do not retag or republish rc10.

## Website / Store language

Product page install commands match **rc15**. Mac App Store **0.1.4 (9)** with engine **0.2.0rc14** is now **READY_FOR_SALE**.
