# Homebrew formula

`runspecimen.rb` installs the sdist
`runspecimen-0.2.0rc13.tar.gz` from the GitHub release `v0.2.0-rc.13`.
That release includes opt-in isolation, policy, and retain. Default backend
`none` does not confine the process.

This file is the formula. Publishing a tap repository is separate.

```bash
brew install --formula ./packaging/homebrew/runspecimen.rb
```

The formula does not enable an OS sandbox. `0.2.0rc13` accepts `isolation`
and `policy`. Published `0.2.0rc12` still rejects those fields.
