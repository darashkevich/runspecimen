# Execution holder split plan (RS-06)

Status: **plan only.** This document does not refactor `src/runspecimen/execution_holder.py`. No module is extracted here. `run_integration_complete` stays false. E2 stays closed. Installed Secure Enclave / biometric admission stays fail-closed. A typed phrase remains refused for `local` / `companion` / `dual`.

`execution_holder.py` is about 4000 lines. It is the in-process core a separate Developer ID product would run. It is not installed by importing the module. An unprivileged test adapter may construct `ExecutionHolder(allow_test_double=True)`. That adapter is not installed protection.

Some process helpers already live beside it: `holder_drop_exec.py`, `holder_supervise_exec.py`, `holder_protocol.py`, `holder_io.py`, `holder_asymmetric.py`, `holder_daemon.py`, `holder_adapter.py`, `holder_entry.py`, `holder_runtime.py`. The remaining blob is one class plus protocol helpers.

## Proposed module boundaries

Keep `ExecutionHolder` as a façade during the move so `handle_message` / `dispatch` and the tests keep one object. Split along operations, not along file size.

### 1. Admission and enrollment — `holder_admission.py`

Owns mutations that change who may later consume, not the consume itself.

| Current methods (approx. lines) | Responsibility |
| --- | --- |
| `enroll` / `_enroll_locked` (~231) | Bootstrap enroll of a caller id. Not human authorization. |
| `begin_human_secure_enclave_enrollment` (~270) | Injected software signer. Installed protection refuses it. |
| `begin_human_operated_native_adapter` (~338) | Human-operated adapter. Not production trust. |
| `enroll_user_invoked_secure_enclave` (~419) | Session control after a person presses a button. Still not D1/D2 closed. |
| `sign_with_os_boundary`, `attach_session`, `sign_from_session` (~593–678) | Session signatures. Software keys stay `hardware: false`. |
| `issue_device_challenge`, `cancel_device_challenge`, `submit_device_signature` (~702–766) | Device challenge mailbox. Peer uid required. |
| `prepare_phone_receipt`, `seal_phone_receipt` (~957–983) | Phone peer receipt. Caller `verified` is not this message. |
| `pair_device`, `replace_device_key`, `rotate_caller`, `revoke_device`, `set_policy` (~1718–2055) | Policy and device lifecycle. Downgrade still needs authorization under the current policy. |
| `accept_native_ipc` (~1408) | Native GUI IPC into the above. Wire JSON cannot select a software double under installed protection. |
| `sign_with_human_operated_adapter`, `sign_with_human_native_signer` (~1550–1640) | Test and session signers. |

Public constants that belong with admission (`DEVICE_CHALLENGE_DOMAIN`, `PHONE_RECEIPT_DOMAIN`, `bound_device_message`, `bound_phone_receipt`) move with this module.

### 2. Consume and execute — `holder_execute.py`

Owns the one-nonce launch path.

| Current methods (approx. lines) | Responsibility |
| --- | --- |
| `issue_exact_run`, `authorize_exact_run`, `exact_run_execute_human` (~1025–1224) | Exact-run challenge, consume, execute. `run_integration_complete` and `e2_closed` stay false on the wire result. |
| `consume` / `_consume_locked` (~2102) | Snapshot, bind, spend nonce, uncertain lease. No typed phrase. |
| `_bind` (~2470) | Workspace input snapshot. Uses `holder_protocol.bind_execution`. |
| `execute` (~2611) | Holder-owned spawn. Privilege drop through `holder_drop_exec`. Supervise through `holder_supervise_exec`. |
| `cancel_uncertain`, `note_child_absent` (~2247–2269) | Lease recovery. |
| spawn / watch / reap helpers (~3375–3735) | Child identity, subreaper, uncertain lease retention. |

`bound_exact_run` and `EXACT_RUN_DOMAIN` move with this module. Do not merge this with admission: enroll must not import spawn.

### 3. Persistence and protocol — `holder_state.py`

Owns durable records and the authenticated message envelope.

| Current pieces (approx. lines) | Responsibility |
| --- | --- |
| `__init__`, `_load`, `_read`, `_write`, `_transaction`, `_validate_record_schema` (~166, ~2313, ~3745–3807) | `meta.json`, `callers.json`, `devices.json`, `spent.json`, `enrollment.json`, `policy.json`, `lease.json`. Mode `0700` on the state root. |
| `caller_secret`, `holder_id`, `generation`, `key_generation` | Record accessors. |
| `message_mac`, `seal`, `open_sealed` (~3810) | HMAC envelope. |
| `dispatch`, `handle_message` (~3849–3995) | Op switch. Stamps `_peer_uid` / `_peer_gid` from the transport, never from the client. |
| `_has_history`, `unlink_replay_history` | Initialization and the test-only replay helper. |

`HolderRefusal` stays a shared error. Protocol version `PROTOCOL = 1` stays here so dispatch can refuse a downgrade before any admission or execute call.

Snapshot files under `run-snapshots/` stay execute's concern; the state module only knows the `0700` enrollment tree.

## What must not move where

- `installed_protection` construction rules stay on the façade: `allow_test_double and installed_protection` remains a `ValueError`.
- Production verifier pin checks stay fail-closed. Do not add a software-key admission path while splitting.
- `run_integration_complete = False` and `e2_closed = False` on `execute-exact-run` stay in dispatch, even if execute lives in another file.
- Agents never type `APPROVE`. Holder ops never accept a phrase (`_human` already refuses `method == "phrase"`).

## Migration steps

Do this as sequential, reviewable extractions. Each step is one PR. Behavior must not change.

1. **Persistence first.** Move `_read` / `_write` / `_transaction` / schema allow-lists into `holder_state.py`. `ExecutionHolder` delegates. Re-run `tests/test_execution_holder.py` and `tests/test_production_boundary.py`.
2. **Envelope next.** Move `message_mac`, `seal`, `open_sealed`, `handle_message`. Keep `dispatch` on the façade until step 4 so op names do not drift.
3. **Execute cluster.** Move consume, execute, exact-run, spawn helpers. Leave `from runspecimen.holder_supervise_exec import GO_BYTE` inside execute. Confirm `tests/test_holder_protocol.py` still binds snapshots.
4. **Admission cluster.** Move enroll, pair, policy, device challenge, phone receipt, native IPC.
5. **Dispatch last.** `dispatch` becomes a thin switch that imports the two clusters. One test file should still construct `ExecutionHolder` only.
6. **Delete empty methods from the façade** only when every caller, including Swift-facing docs, names the façade or an explicit submodule. Prefer keeping the façade until the next version bump so rc15 hashes are not part of this story.

Do not mix a split with a socket-mode change, a biometric prompt, or a holder-receipt path in preflight/postflight.

## Test strategy

The existing suite is the contract. After each extraction:

- `python -m unittest tests.test_execution_holder tests.test_production_boundary tests.test_native_bridge_policies tests.test_holder_protocol tests.test_holder_daemon_accept tests.test_holder_socket_isolation tests.test_isolated_native_enrollment -v`
- No assertion rewrites to go green. If a test imported a private helper, add a re-export on `execution_holder` for one cycle, then point the test at the new module in a follow-up.
- Add a small import-graph test: `holder_admission` must not import spawn helpers; `holder_execute` must not enroll; `holder_state` must not import `native_bridge`.
- Keep skip reasons honest. PyNaCl-absent, Darwin-only, and missing `rsync` skips stay skips.
- A passing unprivileged adapter test is still not installed protection. Do not add a test that sets `e2_closed` or `run_integration_complete` true.

## Out of scope for the split

- Changing `holder.sock` from `0666` (see `docs/HOLDER_SOCKET_MODE.md`).
- Closing E2, D1, or D2.
- Teaching preflight or postflight to accept a holder receipt.
- Moving Swift `HolderSocketClient` or the macOS app onto a new Python module layout in the same PR.
