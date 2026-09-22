# Homebrew formula

`runspecimen.rb` is the in-repo copy of the formula published in the tap
[`darashkevich/homebrew-runspecimen`](https://github.com/darashkevich/homebrew-runspecimen).
Keep them in sync when a release ships.

It installs the published sdist `runspecimen-0.2.0rc13.tar.gz` from GitHub
Release `v0.2.0-rc.13`:

<https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.13/runspecimen-0.2.0rc13.tar.gz>

sha256 `0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5`

That asset is the release sdist. The formula does not point at git `main`.
The release includes opt-in isolation, policy, and retain. Default backend
`none` does not confine the process. The formula does not enable an OS sandbox.
`0.2.0rc13` accepts `isolation` and `policy`. Published `0.2.0rc12` still
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
