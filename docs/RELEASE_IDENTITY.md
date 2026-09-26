# Release identity

Python/plugin cut currently public: **`0.2.0rc14`** / **`v0.2.0-rc.14`**.
This file records what shipped; it does not authorize App Store Connect changes.

## What is live today

| Channel | Identity | Evidence |
| --- | --- | --- |
| GitHub Release | **`v0.2.0-rc.14`** (published prerelease) | https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.14 · tag peels to `25f4013c5c84b89b24024182f7c308dcffe084b4` |
| PyPI | **`0.2.0rc14`** (identical SHA-256 to GitHub) | https://pypi.org/project/runspecimen/0.2.0rc14/ |
| Homebrew tap | **`0.2.0rc14`** (same sdist URL + sha256) | https://github.com/darashkevich/homebrew-runspecimen · `brew tap darashkevich/runspecimen && brew install runspecimen` |
| Product site | `python3 -m pip install runspecimen==0.2.0rc14` | https://runspecimen.darashkevich.com/ (pin update may lag the package publish) |
| Mac App Store | **not public** | Submitted package **0.1.4 (9)** is recorded `WAITING_FOR_REVIEW` (submission `f0bb3ab1-c283-4463-8c27-e5702a35ac6a`, 2026-09-24T12:36:01Z; Apple build `51a18894-02e3-4846-86f5-29cc345567f0`; package SHA-256 `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`). Source was `0f50a2c` plus the rejection fixes, engine **0.2.0rc14**, and it does **not** include evidence expansion. **0.1.3 (8)** was rejected on 2026-09-23. This file was not refreshed from App Store Connect on 2026-09-25. No `apps.apple.com` link. |

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

Product page install commands match **rc14**. Do not add an `apps.apple.com` link until Apple publishes a working URL. The package recorded as waiting for review is **0.1.4 (9)** with engine **0.2.0rc14**, and it does not include evidence expansion. Local **0.1.5 (10)** was an earlier signed app. Local Store package **0.1.5 (11)** from `3a0f483` has SHA-256 `2452956fe1179a7e4e019f5de5b2c40aba460ecbc077a7d75af35458b67ce309` and does not include the later confirmation or pipe fixes. The next candidate is **0.1.5 (12)** and is not uploaded. Do not upload another build while **0.1.4 (9)** is the submission on file. Public website copy should keep the rc14 install pin and must not describe 0.1.5 as available or approved.
