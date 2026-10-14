# qafix31 disposition

This note is not packed into the sdist. It is not a production sign-off and it is not human acceptance. Green tests, a reproducible pack, and a later CI run do not qualify installed, hardware, or Store products. D1 and D2 stay locked. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false.

Parent candidate: `e5fb07dd77f53a0b9d4cb048ed0c587081ae4acb` on PR #66. Independent QA of that commit is `QA-2026-10-12-qafix30-e5fb07d.md`. Verdict there was DO-NOT-SHIP. This table is the disposition of that report. It does not replace a new independent re-QA.

## Findings

| ID | Disposition |
| --- | --- |
| QA30-01 | Fixed. The authenticated install inventories every logical file under `runspecimen` and every site-packages file CPython would import as `runspecimen` before the package directory. A planted `runspecimen/__init__.so` and a sibling `runspecimen.so` fail the check. The canary constructor is not run. An inert `runspecimen.egg-link` is still accepted; an `easy-install.pth` next to it is still refused. Evidence: `tests/test_qafix31.py` on this host, compiled with the system C compiler, Python 3.9. |
| QA30-02 | Fixed. After `pyvenv.cfg` names the trusted interpreter, an adjacent `lib/pythonX.Y` must be that interpreter's standard library. A forged home that only symlinks the executable and plants `sitecustomize.py` is refused. The suspect interpreter is not started, so the canary is not written. A home that aliases the interpreter and has no library tree still uses the compiled-in library (the existing symlink-home test). `/var` and `/private/var` remain the same directory when both names exist. |
| QA30-03 | Fixed. The install hashes the bytes it read. The probe receives those buffers and the launcher body that matched the known template. `after_authenticated_read` is a test seam that mutates the live tree after that read. The drift check refuses and does not start the probe. A later reread is not trusted evidence. Package and launcher canaries stay absent. |
| QA30-04 | Fixed. Installation opens the venv with `O_DIRECTORY|O_NOFOLLOW` and walks every component with `openat` and the same flags. Replacing `venv/lib` with a symlink after the first check raises `InstallRefusal`. The outside directory stays empty. The read-back uses the write descriptor (`O_RDWR`), not a second path lookup. |
| QA30-05 | Fixed as a false qualification, not as demonstrated native-code execution. A regular-file copy of the interpreter is admitted only when its relative loader dependencies still name the trusted base's libraries. `@rpath` and `$ORIGIN` copies are refused. If the loader map cannot be read without executing the file, the copy is refused. Symlinks and hard links to the base are unchanged. This host's Xcode framework copy fails the check and is not executed. The original report's dyld abort was a launch failure, not a successful library canary. |
| QA30-06 | Fixed in `docs/HUMAN-ACCEPTANCE.md`. The sheet now separates the authenticated install, the permitted runtime layout, and the authenticated probe. Loaded origins are realpath-equal to the snapshot. N3-version remains the first execution of the installed launcher, after N3-verify. The stale "must fail when `$WHEEL` is the qafix23 pin" requirement is gone. `command -v runspecimen` stays as an informational line and does not gate the invoked binary. The historical pack name `artifacts/0.2.0rc15-2026-10-12-qafix23/` remains. |
| QA30-07 | Fixed. README, the missing-approval hint in `present.py` and `certificate.py`, FAQ, and `docs/THREAT_MODEL.md` say that inconsistent edits can be detected and that a writer who controls the evidence can fabricate a consistent record. Signature verification and inaccessible-key custody stay separate. The same-user sentence required by the honesty tests remains. |
| QA22-01 through QA22-05 and QA29-01 through QA29-04 | Kept. They are the qafix30 behavior this pack builds on. See `docs/QAFIX30-DISPOSITION.md`. They are not these findings. |
| `launcher_sysconfig` | Left in place. The independent report said it has no in-file caller and was not a current bypass. Removing it is a later cleanup. |
| RQ22-01 pathname/FIFO stall | Unchanged and still acknowledged. Not this batch. |

## Archives

Pack `artifacts/0.2.0rc15-2026-10-12-qafix31/`. Built by Xcode CPython 3.9.6, setuptools 82.0.1, wheel 0.48.0, pip 21.2.4, from the tools venv `/tmp/rs-qafix30-py`. The checker and the smoke install were started from that venv's base interpreter (`/Applications/Xcode.app/Contents/Developer/usr/bin/python3.9`, `-I -S`). Homebrew Python 3.12 is not installed here. This is one macOS host. It is not Debian, Ubuntu, python.org, Homebrew, or CPython 3.10–3.14.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `d9d0c9dfc978beb29ac34901d788e647812d3f663c703281da35d2172ac4f048` |
| `runspecimen-0.2.0rc15.tar.gz` | `9af3d9acd5e6d5d91041e247907c15b48f46219bd123d70a0d1dec95c60b273d` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` |
| `release-report.json` | `f910c6a50e215108c3ca9d953c9e4ebb8f6f07e79a29bbc1df9aaa790ccf8324` |

`shasum -a 256 -c SHA256SUMS` matched. A second build of the same tree reproduced the wheel and the sdist. The plugin is byte-identical to qafix30 (`cmp`). The wheel payload differs from qafix30 wheel `25c6fa06c194146e5750c0a6c05f7cba2ae7e406512639491d455bcae4b462a5` in `runspecimen/present.py`, `runspecimen/certificate.py`, `METADATA`, and `RECORD`. qafix30 was not overwritten.

Local `release_check.py --output-dir /tmp/rs-qafix31-out` exited 0: 933 tests, 36 skipped, 0 failed, then the archive and smoke checks. Skips: 29 PyNaCl, 3 bwrap, 2 Linux `ldd`, 1 pytest, and the holder Mach-O relocation test (this tools-venv layout is not runnable and `/usr/bin/realpath` is absent; a framework CPython whose `@executable_path` libraries resolve still runs that test). Default JSON and `--pretty` refusal tests passed, including the exact N10 line `RunSpecimen error: execution policy local has no typed-phrase fallback` and the separate unknown-field line `contract contains unknown field(s): not_a_real_contract_field`. qafix31 CI has not run yet.

## What this pack does not decide

Human typed approval, hardware acceptance, notarization, install of a real app or daemon, Apple submission, merge, and publication are not done here. A software fixture is not a human approval phrase. Independent re-QA of the new commit is required before any human session. The previous human transcript does not carry forward.
