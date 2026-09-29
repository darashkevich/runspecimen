# Executor protection decision

Status: **Yahor chose guarantee (2). It is not achieved.** Guarantee (3), blocking every equivalent command, is excluded. Mac App Store distribution stays a requirement to validate, not a claim that the current sandbox provides (2). No privileged helper, setuid binary, XPC service, Endpoint Security client, or new entitlement is in this candidate. `consumeForExecution` is not called by a run. `evaluateExecution` only calls a consume function a test supplies, and its `started` field stays false.

Three guarantees are different requirements. This note does not collapse them into one product, and it does not treat Endpoint Security as the only way to isolate a RunSpecimen resource.

## The three guarantees

1. **RunSpecimen's own transition.** The app and CLI refuse to approve, preflight, run, or postflight unless their own gate allows it. Today that gate is the terminal `APPROVE` phrase for a run, and an in-app confirmation for workflow writes. It binds the process that is RunSpecimen. It does not bind any other program.

2. **RunSpecimen's protected resources.** The execution lease is `fcntl` on `.runspecimen/execution.lock` inside the workspace (`src/runspecimen/lease.py`, `LEASE_FILENAME` in `src/runspecimen/paths.py`). Run state, the approval file, and certificates live in that same user-writable `.runspecimen` tree. The goal is that another same-user process cannot overwrite or restore that state, replace the executor that consumes it, replay an approval, race a second consumer, or change policy or enrollment. It does not require Endpoint Security, and it does not stop the user from running the command with `/bin/sh`. Moving the files into the app container does not meet this goal. The probe below shows why.

3. **Every equivalent command on the Mac.** Stopping every process from executing the same argv is global command blocking. That is a different product from (1) and from (2).

Owning a marker or a lease is (2) only for the files the owner can exclusively write. It is not (3). A root-owned marker stops a second `runspecimen` from restoring that file when the user cannot write it. The user can still exec a user-owned command.

## Options, with what each one actually covers

| Option | Guarantee it can support | What it does not do | Cost | Authorized |
| --- | --- | --- | --- | --- |
| Sandboxed Mac App Store app, as it is now | (1) for the app's own buttons and the CLI it launches. The container is the app's sandbox (Guideline 2.5.2). No `com.apple.security.network.server`. | A same-user process can write `.runspecimen` and can exec the command. | None beyond the current app. | Current enforcement. Not guarantee (2). |
| App container, or any directory the same user owns | Does not provide (2). The container is a sandbox between apps, not a barrier against the owning user. | Does not stop overwrite, restore, or replay by an unsandboxed same-user process. | A path change that the probe rejects as proof. | Not sufficient. Not implemented as the (2) design. |
| Privileged helper (`SMJobBless`) holding those files | Can support (2) for files the helper exclusively owns. Apple's archived EvenBetterAuthorizationSample says Mac App Store apps may not use elevated privileges. Guideline 2.4.5(v) forbids root and setuid. Guideline 2.4.5(ii) and (iv) require one self-contained bundle. | Does not stop another process from exec of a user-owned command. Adds a Developer ID install and a second update channel. | Outside this Store app. | Not authorized. Separate decision required before any install. |
| Endpoint Security `ES_EVENT_TYPE_AUTH_EXEC` | (3), by denying execs. It requires the restricted entitlement `com.apple.developer.endpoint-security.client`. WWDC 2020 session 10159: the client is a system extension with a provisioning profile Apple grants separately. DTS forum 759149 (July 2024): that entitlement is not an App Store capability. | It is one way to block execs. It is not a way to protect the lease file. Using it to block the user's own shell is global command blocking. | Restricted entitlement this team does not have. Cannot ship inside this Store app. | Excluded. Yahor chose not to pursue (3). |

QA1773 requires every Mach-O in a sandboxed bundle to be sandboxed. WWDC 2023 session 10266: an XPC service inside `Contents/XPCServices` is replaced when the app is replaced. Neither fact selects among the three guarantees.

## Admin and root

Root can replace a helper, delete its files, and exec anything. An administrator who can install a helper can also run the command directly. Same-user automation and administrator or root compromise are different threats. No design in this document stops root.

A signature still does not prove the person understood the command. Hardware authentication protects the signing operation.

## The decision

Yahor chose guarantee (2) on 2026-09-29, after discussion with Codex. Guarantee (3) is out of scope. The current app still only enforces guarantee (1). This document does not downgrade the goal back to (1), and it does not claim (2) is done.

## Feasibility on this Mac

Probe date 2026-09-29, macOS 27.0, uid 501. The probe created and deleted only its own files. It did not modify `/Applications/RunSpecimen.app` or the approved package.

| Attack | Result |
| --- | --- |
| Same-user process unlinks `.runspecimen/execution.lock` while `Lease.acquire` holds it, then acquires a new file at that path | Both holders report the lease held. The directory entry's inode changed. `fcntl` locks the inode, not the path. |
| Create and delete a file in `~/Library/Containers/com.darashkevich.runspecimen/Data` | Succeeded. The container is owned by the user, mode `drwx------`. |
| User-immutable flag `uchg` on a file this user owns | The write was rejected until the same user ran `chflags nouchg`. |
| Replace `/Applications/RunSpecimen.app` | The bundle is owned by root, mode `drwxr-xr-x`. This uid cannot write it. That protects the installed Store binary from this user. It does not protect workspace state. |

An imported `secure-enclave` label is not attestation. A Secure Enclave private key is not exported by copying a file. A same-user process can still replace the enrollment record, the policy file, and the consumed-approval marker when those files live in a directory that user can write. Root can replace the app, the helper, and those files, and can exec anything. Same-user automation and administrator or root compromise stay different threats. No design here stops root.

Attacker this goal is about: another process running as the same user, including an unsandboxed shell. Not a requirement to stop root. Not a requirement to stop `/bin/sh` from running a user-owned command. That last item is guarantee (3) and is excluded.

## Architecture

This is the design for guarantee (2). It is not installed. The Mac App Store app remains the client. It does not become the owner of trusted state.

| Store | Owner | What a same-user shell may do with it |
| --- | --- | --- |
| Workspace, contract, inputs, captured output | The interactive user | Read and write. These are the command's files, not the trust boundary. |
| Enrollment records: key id, public key, role, generation, backend, provenance, revocation | Dedicated holder principal | Must not rewrite, restore, or roll a generation backward. |
| Selected policy: local, companion, or dual, bound to one Mac identity | Same holder | Must not switch policy by editing a workspace file. |
| Consumed nonces | Same holder | Must not delete or restore a nonce to run the request again. |
| Execution lease for one bounded command | Same holder | Must not replace the lock inode and take a second lease. |

The holder is a Developer ID launch daemon installed outside the Mac App Store bundle. It runs as a system user this interactive user does not own. Its directory is not the app container and not `~`. The Store app and the bundled helper are XPC clients. They are not the process that owns those four stores.

The holder is the process that validates the signed request and launches the bounded command. Validation and consume happen in the holder before `posix_spawn`. The current `src/runspecimen/run.py` path still spawns under the workspace lease. That path stays in place until the holder exists, and it is not guarantee (2).

Callers are authenticated with the XPC audit token and a designated requirement for Team ID `UN6KF8636A`, bundle id `com.darashkevich.runspecimen`, and the bundled helper's identifier. A replacement executable with a different signature is rejected. The user can still start `/bin/sh` themselves. That is guarantee (3), which is excluded.

The holder prevents the workspace attacks as follows.

- Rollback: generation is monotonic in the holder. Copying an older enrollment file into the workspace does not change it.
- Replay: consume is a compare-and-swap of the nonce in the holder before launch. A second consume fails. If the holder crashes after consume and before launch, the nonce stays consumed and recovery is a new signed request. If it crashes after launch, the lease records that the run started and a retry does not launch again.
- Concurrent consumers: one lease token inside the holder.
- Unauthorized policy or enrollment changes: writes require the enrollment path inside the holder. A workspace JSON file is not the policy.

The signed request that the holder accepts binds run id, input fingerprint, contract fingerprint, workspace id, Mac id, bounds, policy, nonce, expiry, and the local and companion key ids and generations. The holder reloads enrollment at consume. Expiry uses the holder's clock. Hardware provenance is the key this Mac or the paired iPhone created in its Secure Enclave during a human enrollment. A file that merely says `secure-enclave` is not that event.

Supported client: macOS 14.0 and later, the app's deployment target. The holder has to be built and installed for the same floor. The feasibility probe ran on macOS 27.0 as uid 501. An app update replaces the client only. Holder state survives that update and the holder has its own update channel. Lost holder state is re-enrollment, not a file restore. Root can replace the holder, its directory, and the client. This design does not stop an administrator or root.

Store compatibility: the helper is not in the Mac App Store bundle, so Guideline 2.4.5 is not asked to allow a setuid tool inside the app. The app stays sandboxed, with no `com.apple.security.network.server` and no relay. If the holder is missing, the app fails closed. It does not fall back to a typed phrase.

## Smallest authorization still required

Authorize one Developer ID launch daemon, outside this Mac App Store app, running as a dedicated system user, owning the enrollment store, policy, consumed nonces, and execution lease, and accepting XPC only from Team ID `UN6KF8636A`'s RunSpecimen client. Do not authorize Endpoint Security, a relay, a listening server, or an entitlement change in the Store app. Do not install the daemon under the current prompt.

These alternatives do not meet guarantee (2), so they are not substitutes: the app container, a user-immutable flag, a keychain item the same user can delete, and calling `consumeForExecution` on files in the workspace. `tests/test_lease.py` records the inode replacement against the current lease. That test passing means the workspace lease is still bypassable. It is not a passing protection test.

Until that holder exists, these are not proof of (2): moving files into the container, a passing `fcntl` test, a software consume, or a Boolean named as a human tap. `consumeForExecution` stays unwired. The run path still asks for a typed phrase in a terminal. That phrase is the current guarantee (1) gate. It is not the biometric policy below, and it must not become a silent fallback once a biometric policy is required.

## Approval policy

This is the chosen policy. It is not yet what `runspecimen run` enforces.

| Run | Approval |
| --- | --- |
| Default | Local Mac Touch ID |
| Explicitly selected alternative | Paired iPhone |
| Sensitive run | Dual policy: both the Mac and the paired iPhone, two distinct devices |

When a biometric policy is required, a typed phrase does not replace it. Pairing is a person comparing matching device and key fingerprints on both screens, then an authenticated enroll, replacement, or revocation. Key trust stays separate from hardware provenance. A carried file that says `secure-enclave` is `carried-pin` / `unverified` unless this device performed the enrollment. Transport starts as files a person carries. There is no relay and no listening server. Approval on the iPhone is not physical presence at the Mac.

The approval must bind the exact run, inputs, contract, workspace, policy, bounds, nonce, and expiry, and be consumed atomically with execution authorization. Replay of a consumed approval fails. That integration waits on a holder that makes the consume marker meaningful against another same-user process. Wiring it to today's user-writable lease would label guarantee (1) as guarantee (2).

## Human session, after the holder exists

One identified Mac build and one identified iPhone build, with hashes. The person runs success, cancel, restart, rotation, revoke, old-key rejection, local, companion, and dual policies, one harmless disposable bounded run, and a rejected replay. Both devices need real acceptance if both ship. An agent does not trigger biometrics, enter the approval phrase, handle credentials, or write the human evidence.

Mac App Store distribution of the final candidate remains required for validation. Passing that check will not, by itself, mean guarantee (2) is true.
