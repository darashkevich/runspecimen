# Homebrew formula

`runspecimen.rb` is the in-repo copy of the formula published in the tap
[`darashkevich/homebrew-runspecimen`](https://github.com/darashkevich/homebrew-runspecimen).
Keep them in sync when a release ships.

It installs the published sdist `runspecimen-0.2.0rc14.tar.gz` from GitHub
Release `v0.2.0-rc.14`:

<https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.14/runspecimen-0.2.0rc14.tar.gz>

The public tap [`darashkevich/homebrew-runspecimen`](https://github.com/darashkevich/homebrew-runspecimen)
is the install source of truth for `sha256`. Because this formula file is also
bundled inside the sdist (MANIFEST), the in-tree `sha256` cannot be a
self-digest of that same archive; after the GitHub Release is published, the
tap (and a follow-up commit) record the real sdist digest from `SHA256SUMS`.

Published sdist sha256 `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3`.

That asset is the release sdist. The formula does not point at git `main`.
The release includes opt-in isolation, policy, and retain. Default backend
`none` does not confine the process. The formula does not enable an OS sandbox.
`0.2.0rc14` accepts `isolation` and `policy`. Published `0.2.0rc12` still
rejects those fields.

## Install from the tap

```bash
brew tap darashkevich/runspecimen
brew install runspecimen
```

Or:

```bash
brew install darashkevich/runspecimen/runspecimen
```

## Install from this checkout (no tap)

```bash
brew install --formula ./packaging/homebrew/runspecimen.rb
```
