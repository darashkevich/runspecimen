# qafix30 disposition

This note is not packed into the sdist. It is not a production sign-off. Green tests and a green CI run do not qualify installed, hardware, or Store products. D1 and D2 stay locked. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false.

Parent candidate: `5244fb06b1a8c9ac97c45734d2ee8abc5e606466` (PR #63). The independent qafix29 report was not in the workspace when this batch was written. QA29-01 through QA29-04 below are the install-to-verification defects named in the consolidation request. A later report must be folded in before a human session; do not treat this table as that report.

## Findings

| ID | Disposition |
| --- | --- |
| QA22-01 | Kept. A shebang argument is refused before execution. `tests/test_qafix30.py` checks a canary file is not created. |
| QA22-02 | Kept. `python2` and any interpreter that is not the trusted base are refused. The canary is not executed. Name and template are not treated as interpreter identity (`selected_interpreter_findings`). |
| QA22-03 | Kept. N3-verify still precedes `rs --version`. The sheet no longer runs target-venv Python or pip before that step. |
| QA22-04 | Kept. Event-log lock is released when file setup fails. Not reopened. |
| QA22-05 | Kept in `present.py`, the dashboard, and About. FAQ and `docs/THREAT_MODEL.md` now use the same qualified wording: inconsistent edits can be detected; a same-user rewrite can fabricate consistent evidence. |
| QA29-01 | Fixed. The sheet and `release_check.py` smoke create the venv with `base -I -S -m venv --without-pip` and install with `scripts/install_pinned_wheel.py` under `-I -S`. `-I` alone is refused by the installer. The target venv's Python and pip are not started before static verification. |
| QA29-02 | Fixed. The `rm -rf … setuptools* … \|\| true` step is gone. An existing venv, an existing launcher, pip, or an existing package is a refusal. Unmatched globs are not used. |
| QA29-03 | Fixed. The installer authenticates the pinned sha256 before writing. It rejects traversal, duplicates, links, unexpected members, overwrites, symlinked destination ancestors, and oversized members. It writes only inside the new venv, emits the distlib console-script body, and does not import the wheel. |
| QA29-04 | Fixed. Every admitted `runspecimen*` / `pip*` launcher's selected interpreter must be the trusted base or a byte copy of it. A pip launcher is an unnecessary executable and fails the check. The probe runs a private copy of the bytes that matched the wheel and does not start if those bytes changed. The check is documented as point-in-time, not persistent execution protection. |
| qafix29 macOS 3.11 timeout | Recorded, not described as green. Push run [38279619647](https://github.com/darashkevich/runspecimen/actions/runs/38279619647) failed: unittest cap 600s expired while `test_compiled_package_relocates_runtime_without_a_developer_interpreter` was still copying files. Pull request run [38279624560](https://github.com/darashkevich/runspecimen/actions/runs/38279624560) succeeded. The cap is now 900s and the release-check job cap is 30 minutes. That is headroom for a test that was still making progress, not a claim that the push run passed. |
| Independent qafix29 report | Not available in this workspace. No extra findings were invented. Re-QA has to supply anything this table missed. |

## Archives

Pack `artifacts/0.2.0rc15-2026-10-12-qafix30/`. Built by Xcode CPython 3.9.6, setuptools 82.0.1, wheel 0.48.0, pip 21.2.4, from the tools venv `/tmp/rs-qafix30-py`. Homebrew Python 3.12 is not installed here (`/tmp/rs-py312-rel-holder/bin/python3.12` is a broken symlink). The smoke install and the static check were started with `/Applications/Xcode.app/Contents/Developer/usr/bin/python3.9` (`-I -S`), because the tools venv is not an accepted checker.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `25c6fa06c194146e5750c0a6c05f7cba2ae7e406512639491d455bcae4b462a5` |
| `runspecimen-0.2.0rc15.tar.gz` | `268f7b336e4c3f115055b280cf1ec721851999415de47991511a59bc30aa7fc4` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` |

`shasum -a 256 -c SHA256SUMS` matched. The plugin is byte-identical to qafix29 (`cmp`). The wheel payload matches qafix29 wheel `3759ea01c7032b2b8f37482fbb32825fdef0508568cd4b505847a9f463c241f8`; the whole-file hash differs by the setuptools 82.0.1 `WHEEL` Generator line. qafix29 sdist `690b3f56fb965114c8808f526c3580d9e2b65b29e9651578b540b804450aaecd` was not overwritten. `src/` was not changed.

Local `release_check.py --output-dir /tmp/rs-qafix30-out` exited 0: 925 tests, 36 skipped, 0 failed, then the archive and smoke checks. Skips include PyNaCl, pytest, Linux `ldd`, and the holder Mach-O relocation test (this venv's `@executable_path` layout is not runnable and `/usr/bin/realpath` is absent; CI framework Pythons still run it). This is one macOS host and CPython 3.9.6. It is not Debian, Ubuntu, python.org, Homebrew, or CPython 3.10–3.14. The acceptance sheet's success path and the missing-wheel / existing-venv refusals passed in bash and in zsh with nomatch. qafix30 CI has not run yet.

## What this pack does not decide

Human typed approval, hardware acceptance, notarization, install of a real app or daemon, Apple submission, merge, and publication are not done here. Software fixtures are not human approval. The previous human transcript does not carry forward.
