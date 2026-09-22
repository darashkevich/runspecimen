# homebrew-runspecimen

Draft tap layout. While this file lives at `packaging/homebrew/tap-draft/`
inside the RunSpecimen repository, this directory is not itself a published
tap. `brew install` from the internet still needs a tap. Copy this directory's
contents to the root of a new `homebrew-runspecimen` repository by hand. Do
not push that repository from the RunSpecimen tree, and do not run
`brew tap-new` here.

After that repository exists on GitHub:

```bash
brew tap <github-user>/runspecimen
brew install <github-user>/runspecimen/runspecimen
```

`Formula/runspecimen.rb` installs the published sdist
`runspecimen-0.2.0rc13.tar.gz` from GitHub Release `v0.2.0-rc.13`:

<https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.13/runspecimen-0.2.0rc13.tar.gz>

sha256 `0a807d65e73adfc2af2c8e5679706ed7c4d881ffefdc36e9222507cf5168f5c5`

The formula URL is that release asset. It does not point at git `main`.
The formula does not enable an OS sandbox. Default backend `none` does not
confine the process. `0.2.0rc13` accepts `isolation` and `policy`. Published
`0.2.0rc12` still rejects those fields.

Until the tap exists, install from a RunSpecimen checkout:

```bash
brew install --formula ./packaging/homebrew/runspecimen.rb
```
