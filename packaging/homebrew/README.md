# Homebrew formula

`runspecimen.rb` is the in-repo copy of the formula for the tap
[`darashkevich/homebrew-runspecimen`](https://github.com/darashkevich/homebrew-runspecimen).
Keep them in sync when a release ships.

It installs the published PyPI sdist `runspecimen-0.2.0rc16.tar.gz`:

<https://files.pythonhosted.org/packages/73/b5/963b42b37a0a932e22496f7da4d3c289fef01b1a87d31f6914571ed3081d/runspecimen-0.2.0rc16.tar.gz>

sha256 `83625441d316816107087870525a88d20cd42b61c69e7e398ce95cdcc3fe31d4`

The public tap [`darashkevich/homebrew-runspecimen`](https://github.com/darashkevich/homebrew-runspecimen)
is the `brew install` source of truth. Because this formula file is also
bundled inside the sdist (MANIFEST), the in-tree `sha256` cannot be a
self-digest of that same archive; after the PyPI/GitHub cut is published, a
follow-up commit records the real sdist digest from PyPI JSON and
`SHA256SUMS`. Copy the same `url` / `sha256` into the tap's
`Formula/runspecimen.rb`.

That asset is the published sdist (GitHub Release `v0.2.0-rc.16` bytes are
identical). The formula does not point at git `main`. This cut includes the
supervisor cleanup fix for
[GHSA-8357-m9wf-gjh9](https://github.com/darashkevich/runspecimen/security/advisories/GHSA-8357-m9wf-gjh9).
Default backend `none` does not confine the process. The formula does not
enable an OS sandbox. `0.2.0rc16` accepts `isolation` and `policy`. Published
`0.2.0rc12` still rejects those fields. Runtime `project.dependencies` is
empty, so this formula has no `resource` blocks.

## Install from the tap

```bash
brew tap darashkevich/runspecimen
brew install runspecimen
```

Or:

```bash
brew install darashkevich/runspecimen/runspecimen
```

The live tap still needs a matching `Formula/runspecimen.rb` commit before
`brew install` serves rc16.

## Install from this checkout (no tap)

```bash
brew install --formula ./packaging/homebrew/runspecimen.rb
```
