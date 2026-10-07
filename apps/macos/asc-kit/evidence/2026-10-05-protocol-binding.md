# Protocol-binding follow-up

This note is not a production sign-off. Canonical package hashes are in `docs/CANDIDATE_MANIFEST.md`. The sdist does not contain that file or its own hash.

Built with Homebrew Python 3.12.14 at `/tmp/rs-py312-rel-holder`. `python3 -m unittest discover -s tests -v`: 640 tests, 0 failures, 35 skipped (PyNaCl 29, bubblewrap 3, pytest 1, Linux ldd 2). No 3.11 or 3.14 suite was skipped to go green. `rsync` and `swiftc` were present, so holder stage tests ran. Apple `/usr/bin/python3` was not used to freeze.

| File | SHA-256 | Versus the prior seal |
| --- | --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `eb0a42cc87ffc2700ab35550b4ed5515d156f4681e31ffc84021dfac3397b191` | changed |
| `runspecimen-0.2.0rc15.tar.gz` | `92f03e69ab55a0246ec6cfdd918031d70d05617ee8e20ca617fa1f252dfc5038` | changed |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `a3c194600d70c77a74fc9cce00442ba716cdb2596760b766b93a45a52c7b5db2` | changed |

Directory: `artifacts/rc15-2026-10-05-qa-py312-protocol/`. No new stage tar. Prior sealed stage `5200682fec6d5cdeee72c81ea8a419b0b2d80022f648f77a75a783b4eee9cdc9` was not overwritten.

Installed admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false. Bundle id `com.darashkevich.runspecimen.holder` is accepted for Developer ID packaging only. `production_verifier_pin()` stays team `UN6KF8636A` and `com.darashkevich.runspecimen.native-p256-verify`. No Aqua Secure Enclave product was added. The live apps were not replaced. This is not installation qualification.
