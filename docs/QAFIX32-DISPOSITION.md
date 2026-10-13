# qafix32 disposition

This note is not packed into the sdist. It is not a production sign-off and it is not human acceptance. Green tests, a reproducible pack, and a later CI run do not qualify installed, hardware, or Store products. D1 and D2 stay locked. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false.

Starting candidate: `7d2fdde587fe112605a3f07cf9749a542793dbff` on PR #67. Git tree `1de4fbf1c75079ba3e31b8f02e9096e51f804ddd`. `src/` tree `44a4fb192c2d4e7e56a3124bec66c9280d205836`. Independent QA of that commit is `QA-2026-10-12-qafix31-7d2fdde.md`. Verdict there was DO-NOT-SHIP. Green CI on that commit is not evidence these findings were fixed. This table is the disposition of that report. It does not replace a new independent re-QA.

## Findings

| ID | Disposition |
| --- | --- |
| QA31-01 | Fixed. `_home_stdlib_findings` walks parents from `pyvenv.cfg` `home` as written, first for `platlibdir/pythonXY.zip`, then for `os.py` or `os.pyc`. The first landmark's standard library must be the trusted base. No landmark is the compiled-in library and stays accepted. A missing adjacent `os.py` is not treated as safe. The suspect interpreter is not started. On the starting verifier, the parent-directory home and the `os.pyc`-only home both returned `ok`. After the change, `tests/test_qafix32.py` refuses both before the launcher runs and the planted marker stays absent. The existing adjacent forged home and the symlink-only home still behave as before. This host's framework 3.9 did not execute those hooks in the original report; the tests still refuse both layouts here without executing them. CPython 3.11.10 was not available on this machine, so the original hook execution was not re-run. |
| QA31-02 | Fixed. `_package_inventory` records a nested directory inode the second time it appears, under its logical import name, instead of skipping it. `runspecimen/cli` pointing at `.` fails with `extra_files` before the launcher is invoked, and the marker stays absent. A whole-package symlink whose bytes match the wheel still verifies. An inert `runspecimen.egg-link` is unchanged. The original report showed a different imported module (`cli/__init__.py`), not arbitrary-code execution. |
| QA31-03 | Fixed as a loader-layout refusal, not as demonstrated constructor execution. `_at_trusted_executable_path` admits a symlink only when its real path is the trusted executable's own path. A hard link shares the inode but keeps its own path, so it takes the same relative-loader check as a byte copy. On this host's macOS framework Python 3.9, `os.link` of the framework interpreter into `venv/bin/python` fails verification and the message contains `hard link`. The hard link is not executed, and no library constructor was planted. A standalone 3.11 hard link was not reproduced here; the original report said that layout continued to run. Absolute or soname-only copies can still verify because those dependencies do not move. |
| QA31-04 | Fixed in `docs/HUMAN-ACCEPTANCE.md` and `docs/THREAT_MODEL.md`. The sheet separates the static layout read from the probe. The probe executes captured wheel bytes and the known launcher body with the trusted base interpreter. It does not use the launcher's interpreter and it does not observe the live venv. N3-version remains the first execution of the installed launcher, after N3-verify. |
| QA30-01 through QA30-07 | Kept. They are the qafix31 behavior this pack builds on. See `docs/QAFIX31-DISPOSITION.md`. QA30-05's note that hard links were unchanged describes that pack, not this one. |
| `launcher_sysconfig` | Left in place. The independent report said it has no in-file caller and was not a current bypass. Removing it is a later cleanup. |
| RQ22-01 pathname/FIFO stall | Unchanged and still acknowledged. Not this batch. |

## Archives

Pack `artifacts/0.2.0rc15-2026-10-12-qafix32/`. Built by Xcode CPython 3.9.6, setuptools 82.0.1, wheel 0.48.0, pip 21.2.4, from the tools venv `/tmp/rs-qafix30-py`. The checker and the smoke install were started from that venv's base interpreter (`/Applications/Xcode.app/Contents/Developer/usr/bin/python3.9`, `-I -S`). `src/` is unchanged from qafix31, so the wheel is byte-identical to qafix31. The sdist changed because `scripts/verify_installed_wheel.py`, the tests, `CHANGELOG.md`, and `docs/THREAT_MODEL.md` are packed.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `d9d0c9dfc978beb29ac34901d788e647812d3f663c703281da35d2172ac4f048` |
| `runspecimen-0.2.0rc15.tar.gz` | `7abe59f54e974140e305f3b31f24767ca078eaafe0b606c26f606cb1ece9e63b` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` |
| `release-report.json` | `b1b08fe4846d4be9f18e2e1e0ee58051607f88e256349e69ffda1229c9d63968` |
| `SHA256SUMS` | `dd8b9d3057b060910476f683baf358b03c151ccf39c41267ad05eed8a18cc593` |

`shasum -a 256 -c SHA256SUMS` matched. A second build of the same tree reproduced the wheel and the sdist. The plugin is byte-identical to qafix31 (`cmp`). qafix31 was not overwritten.

Local `release_check.py --output-dir /tmp/rs-qafix32-out` exited 0: 938 tests, 36 skipped, 0 failed, then 4 distribution tests. The 938 count is the previous 933 plus the five qafix32 tests, collected once. Skips: 29 PyNaCl (24 `PyNaCl not installed`, 5 `pip install 'runspecimen[ed25519]'`), 3 bwrap, 2 Linux `ldd`, 1 pytest, and the holder Mach-O relocation test (this tools-venv layout is not runnable and `/usr/bin/realpath` is absent; a framework CPython whose `@executable_path` libraries resolve still runs that test). Default JSON and `--pretty` refusal tests passed, including the exact N10 line `RunSpecimen error: execution policy local has no typed-phrase fallback` and the separate unknown-field line `contract contains unknown field(s): not_a_real_contract_field`.

A clean `/usr/bin/python3` 3.9.6 venv, created with `-I -S -m venv --without-pip`, installed the pinned wheel without running the venv, verified with this checkout's verifier, and then `bin/runspecimen --version` printed `runspecimen 0.2.0rc15` and exited 0. python.org 3.11–3.14 are not installed here. Homebrew is installed and has no Python formula. This host is not Debian or Ubuntu. Those combinations are unverified on this machine. Mocks were not used as a substitute.

The first push of this branch, `e201ae36d6b20bc12a19865e9a426a39f8aa2eed`, failed only Ubuntu 3.12 release-check (push run 38320877479, pull request run 38320885566). `test_rq1703_symlinked_interpreter_home_is_accepted` expected acceptance, and the verifier refused because the `/tmp` home walk selects `/lib/python3.12`, which is not the trusted library on that runner. The other jobs on that SHA passed, including Ubuntu 3.9, 3.10, 3.11, 3.13, and 3.14 and macOS 3.11 and 3.14. The test now expects that refusal when the walk selects a foreign library, and still expects acceptance when the walk finds no landmark. This host's framework 3.9 has no such landmark, and the test still accepts the fixture here.

## What this pack does not decide

Human typed approval, hardware acceptance, notarization, install of a real app or daemon, Apple submission, merge, and publication are not done here. A software fixture is not a human approval phrase. Independent re-QA of the new commit is required before any human session. The previous human transcript does not carry forward.
