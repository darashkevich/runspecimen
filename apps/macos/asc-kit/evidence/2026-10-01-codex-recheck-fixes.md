# Codex recheck fixes (PR #39 comment 5930799635)

Parent tip before this pass: `b9452205b3a85c99f896856b96c285969de2db80`.
This note is not production sign-off, not Store parity, and not an installed holder.
Nothing here was installed, notarized, merged, or submitted. No approval phrase was typed.
No Touch ID, Face ID, or paired-phone prompt was run.

Focused regressions: `artifacts/rc15-2026-10-01-qa-py312-codex/focused-regressions.txt` (81 tests, OK).
`release_check` on Homebrew Python 3.12.14 (`/tmp/rs-py312-rel-holder`): 522 tests, 35 skipped, then 4 distribution-artifact tests. PyNaCl, bubblewrap, and Linux ldd were skipped. Apple `/usr/bin/python3` was not used to freeze.

| Artifact | SHA-256 |
| --- | --- |
| wheel `runspecimen-0.2.0rc15-py3-none-any.whl` | `d014e8b5361853a08c44c173dc0cecec890be3acbe2b6016c4ab9c8e9cab3e37` |
| sdist `runspecimen-0.2.0rc15.tar.gz` | `4f755211c135296c971f970b95bd1f49610a3cf7fd1c95196b086dc5d2c048af` |
| plugin `runspecimen-plugin-0.2.0-rc.15.zip` | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged. No Store package was created.

## 1. Forged-signature acceptance

Handwritten Ed25519 verify/sign is gone. `verify_device_signature` returns false unless PyNaCl is present and the signature checks. Invalid keys and invalid signatures return false. Production pairing fails closed with `vetted device verifier is not connected` when PyNaCl is absent. A software test double is refused when `installed_protection` is set. HMAC, software Ed25519, and an imported hardware label are not a Secure Enclave.

Tests (OK): `test_identity_point_forge_is_rejected_without_handwritten_verifier`, `test_production_rejects_software_test_double`, `test_hmac_is_rejected_for_local_policy`, `test_bootstrap_and_signed_local_execute_from_snapshots`.

## 2. Reparented descendant supervision

A process-group check is not treated as proof. `ps` failure or an empty table is uncertainty. Pids observed before the parent exits stay in the set, so a setsid child reparented to init is not dropped. Uncertainty retains the lease (`child=supervision-uncertain`, `descendants_absent=false`) and a restarted holder refuses the next consume.

Tests (OK): `test_inspection_failure_retains_the_lease`, `test_reparented_pid_is_outside_the_post_wait_tree`.

## 3. World-readable snapshots

Per-run snapshots are sealed without group or world bits and do not contain enrollment, policy, spent nonces, or leases. The snapshot parent is `0711` so a payload can traverse a known path without listing nonce names. State stays `0700`. Mode bits are what an unprivileged test can prove. A second uid was not switched.

Test (OK): `test_snapshot_is_not_world_readable_and_omits_protected_state`.

## 4. Production socket override

`installed_socket_path()` does not read `RS_HOLDER_SOCKET`. PR #44's production override was not merged. Tests construct a client path directly.

Test (OK): `test_production_socket_path_ignores_env_override`.

## 5. iOS scanner negative fixtures

`apps/ios/Scripts/nm_symbol_gate.py` treats a missing, unreadable, or non-Mach-O target as fatal, caches one successful `nm` result, and rejects forbidden names. No iOS app was installed. No provisioning update. This is not a device Release proof.

Tests (OK): `test_forbidden_symbol_is_fatal`, `test_missing_object_is_fatal`, `test_non_mach_o_is_fatal`, `test_unreadable_object_is_fatal`, `test_clean_mach_o_object_passes_and_is_cached`.

## 6. Reviewed follow-ups

Daemon `accept` returns to the loop on `socket.timeout` and `TimeoutError`. Other accept errors propagate. A repeated timeout can be followed by a connection. PR #40's inflight STATUS note and PR #41's `--expected-commit` alias are included. PR #43's Swift capture-failure tests are in the tree and were not run in this Python `release_check`.

Tests (OK): `test_accept_returns_none_on_deadline`, `test_non_timeout_accept_error_propagates`, `test_repeated_timeout_then_successful_connection`, `test_python39_accept_raises_socket_timeout_not_timeout_error`, `test_deprecated_expect_commit_alias_warns_once`.

## 7. Secure Enclave path

Local, companion, and dual production verification fail closed when no vetted verifier is connected. The software test double is not hardware. A typed phrase is still refused when `execution_approval` is set. Policy downgrade still needs authorization under the current policy. Caller expiry uses the holder clock. Bootstrap still authorizes enroll and pair only. No human biometric was run.

## 8. Runtime trust

Ownership, mode, and symlink checks stay in `holder_runtime.py`. The live install was not repaired.

Tests (OK): `test_symlink_mode_and_injection_fail_closed_together`, `test_group_writable_component_is_refused`.

## GUI

Development-signed app, not installed:

`/tmp/rs-qa-codex-20261001/DerivedData/Build/Products/Release/RunSpecimen.app`

Authority `Apple Development: jahorka@gmail.com (PK6W7JVY6D)`, Team `UN6KF8636A`. Sandbox true. `com.apple.security.network.server` absent. `get-task-allow` was not added; the re-sign used `RunSpecimen.mas.entitlements`. Main executable SHA-256 `5849fb8ca64f91ebe5be82748f17e7c29d82caff2805dfa71ad03f418aba217a`. Version string 0.1.5 (13) does not identify the source. Channel `mas`. The bundle contains no holder. Launch pid 62001 was killed. The container `~/Library/Containers/com.darashkevich.runspecimen` was restored. This is not holder acceptance and not the older `91081f5` GUI.

`/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. `/Applications/RunSpecimen Holder.app` mtime stayed 2026-09-30 15:19:13. Daemon pid 42554 was not signaled.

## Live repair (not performed)

“I approve everything” is not confirmation to do this. These steps were not run.

1. Boot out the system daemon only after confirming the label, for example `sudo launchctl bootout system/com.darashkevich.runspecimen.holder.daemon`. Do not use a signal to pid 42554 as that step.
2. Replace only `/Applications/RunSpecimen Holder.app` with a build of this candidate whose entrypoint is `python -I` on the bundled `holder_entry.py`. Do not replace `/Applications/RunSpecimen.app`.
3. Root-own `Contents/Resources`, the interpreter, and the module path. Keep holder state mode `0700`. Keep `run-snapshots` mode `0711` (traverse, not list). Seal each per-run tree to the authenticated payload user with no group or world bits and no write bit (`0500` directories, `0400` or `0500` files). Do not chmod snapshots `0755`; that lists nonce names.
4. Prove the console user cannot write the interpreter or the module path.
5. Start the daemon only after those checks pass.
