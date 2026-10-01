# QA comments after 356ebdb

Comments:

- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5933484882 (2026-10-01T14:25:38Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5933495229 (2026-10-01T14:26:13Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5933495691 (2026-10-01T14:26:15Z)

PRs #40–#45 had no issue comments, review comments, or reviews newer than 2026-10-01T13:55:59Z. Pull request #39 had no new review comments or reviews after that timestamp.

Code SHA: `b1f075ebd320c371106d6ca045048cc6382e970b`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. No Secure Enclave private key was created. The live holder was not repaired. CI green is not readiness.

## Already satisfied on 356ebdb

The closed gate requires the go byte. A relative interpreter is refused before spawn. The signed snapshot execute uses an absolute interpreter and includes stderr. CryptoKit P-256 stays labeled not-hardware, and `installed_protection` still refuses a software P-256 key. `hardware=True` stays refused. Production `installed_socket_path()` still ignores `RS_HOLDER_SOCKET`.

## Fixed

1. **Unclosed pipes on spawn failure.** The spawn-failure path reaped the child and raised before the read-loop `finally`, so stdout and stderr stayed open and Python warned on collection. Those pipes are now closed in a `finally` on that path, including when the lease is retained. The duplicate `import sys` is gone. Tests: `test_unarmed_spawn_reaps_without_running_and_keeps_a_living_child` failed on the unclosed-file warnings before the close and passed after (OK).

2. **Live socket isolation is test-only.** `test_policy_without_holder_does_not_spawn_or_accept_a_phrase` patched `installed_socket_path` to a missing temp path and now expects the missing-socket refusal. New tests in `tests/test_holder_socket_isolation.py`: `test_production_path_stays_live_while_tests_inject_a_temp_socket`, `test_missing_socket_fails_closed_without_the_live_path`, `test_socket_present_without_caller_env_fails_closed`, `test_unenrolled_caller_fails_closed_on_a_temp_adapter`, `test_named_policy_hardware_true_fails_closed` (local, companion, dual). `cli.py` still calls `run_contract` without a holder. `_human_for` still claims `hardware: True` and is not a biometric. Production does not read `RS_HOLDER_SOCKET`.

## Not implemented

Comment 5933484882 also asks for a real Secure Enclave enrollment path, a prebuilt verifier, and pairing persistence. Comment 5933495691 says this push adds no new holder features and does not expand pairing. No Secure Enclave private key was created. The production path remains fail-closed for `hardware=True`, an imported secure-enclave label, and a software P-256 key when installed protection is on. Runtime `swiftc` is still the CryptoKit check, and it is not a Secure Enclave.

Comment 5933495691 said not to add another artifacts tree. The parent task required a new directory because holder source changed. The new directory does not overwrite `artifacts/rc15-2026-10-01-qa-py312-gate`.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 535 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-pipes/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `46fa02e8579b0e1c42e4713b5a32d26e921eca155488db4706776b2e286f9bf1` |
| sdist | `bdc95269e33cce330ca7da4a026be5dd11c61b2f80bb48e641fd590a5e9eda65` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged. No Store package.

The macOS GUI app sources did not change. The previous development GUI remains the build of `27bb0c7` app sources. This pass does not claim a new GUI acceptance.

PRs #40, #41, #42, #43, and #45 were already present on this branch and are marked superseded. PR #44 stays open because its production `RS_HOLDER_SOCKET` override was not taken.
