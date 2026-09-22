# Homebrew formula

`runspecimen.rb` installs the **published** sdist
`runspecimen-0.2.0rc12.tar.gz` from the GitHub release `v0.2.0-rc.12`.
That release does not include the unreleased isolation, policy, or retain
commands in this working tree. Those land in a later tag.

This file is the formula. Publishing a tap repository is separate.

```bash
brew install --formula ./packaging/homebrew/runspecimen.rb
```

The formula does not enable an OS sandbox. Published `0.2.0rc12` still rejects
unknown contract fields, including `isolation` and `policy`.
