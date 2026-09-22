# Homebrew formula

`runspecimen.rb` installs the published sdist
`runspecimen-0.2.0rc13.tar.gz` from GitHub Release `v0.2.0-rc.13`:

<https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.13/runspecimen-0.2.0rc13.tar.gz>

sha256 `0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5`

That asset is the release sdist. The formula does not point at git `main`.
The release includes opt-in isolation, policy, and retain. Default backend
`none` does not confine the process.

This directory is not itself a published tap. `brew install` from the internet
still needs a tap. `runspecimen` is not in homebrew-core. Publishing a
`homebrew-runspecimen` repository is a separate human step. Do not `brew tap`
this directory against GitHub, and do not run `brew tap-new` from this tree
(that command can create a GitHub repository).

From a checkout of this repository, without a tap:

```bash
brew install --formula ./packaging/homebrew/runspecimen.rb
```

The formula does not enable an OS sandbox. `0.2.0rc13` accepts `isolation`
and `policy`. Published `0.2.0rc12` still rejects those fields.

## Tap layout to copy later

`tap-draft/` is a skeleton a human can copy into a new repository named
`homebrew-runspecimen`. Copying it does not publish a tap. The canonical
formula pin stays `packaging/homebrew/runspecimen.rb`.
`tap-draft/Formula/runspecimen.rb` is the same formula (same release URL,
version assertion, and sha256).

```text
homebrew-runspecimen/
  README.md
  Formula/runspecimen.rb
```

After a human creates that repository on GitHub:

```bash
brew tap <github-user>/runspecimen
brew install <github-user>/runspecimen/runspecimen
```
