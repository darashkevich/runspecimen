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
| Embedded `SMAppService` root daemon plus an app-group Mach service | Can support (2) if the payload runs as the console user and the holder state is root mode `0700`. The binary stays in the bundle. | Guideline 2.4.5(v) still forbids requesting root. A persistent daemon has to be reconciled with 2.4.5(iii). The current app has no app-group entitlement, and a measured sandboxed lookup failed while an unsandboxed client succeeded. | New entitlement and a root helper. Review acceptance is not shown. | Not authorized. The decision is in "Smallest authorization still required". |
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

This is the design for guarantee (2). It is not installed. Nothing in this section authorizes building it. The Mac App Store app remains a client. It does not own trusted state, and it does not launch the bounded command.

| Store | Owner | What a same-user shell may do with it |
| --- | --- | --- |
| Workspace, contract, inputs, captured output | The interactive user | Read and write. These are the command's files, not the trust boundary. |
| Enrollment records: key id, public key, role, generation, backend, provenance, revocation | Holder, as root, mode `0700` | Must not rewrite, restore, or roll a generation backward. |
| Selected policy: local, companion, or dual, bound to one Mac identity | Same holder | Must not switch policy by editing a workspace file. |
| Consumed nonces | Same holder | Must not delete or restore a nonce to run the request again. |
| Execution lease for one bounded command | Same holder | Must not replace the lock inode and take a second lease. |

The holder has to run as root. A dedicated unprivileged user can own the files, but it cannot `setuid` the payload to the console user. If the payload ran as the holder, it would inherit write access to enrollment, policy, nonces, and leases. That fails the identity requirement. The public SDK on this Mac does not declare `posix_spawnattr_set_uid_np`. The spawn path is `fork`, then in the child `setgroups`, `setgid`, and `setuid` to the console user taken from the XPC audit token, then `exec` of a signed wrapper. The parent stays root and does not pass the child a file descriptor for the holder directory. The child's environment does not include holder sockets or tokens. After `setuid`, a mode `0700` root directory is not writable by the payload.

The wrapper is a signed binary inside the root-owned app bundle. It waits on a pipe. The holder sends one go byte only after the checks below. The wrapper then `exec`s the exact signed argv. A same-user replacement of that wrapper fails the holder's code-signature check before `fork`. The user can still start `/bin/sh` themselves. That is guarantee (3), which is excluded.

Callers are authenticated in two steps, and the first step is not human authorization. The XPC audit token must match Team ID `UN6KF8636A`, bundle id `com.darashkevich.runspecimen`, and the bundled helper identifier. A replacement executable with a different signature is rejected. Enrollment, policy changes, and runs additionally require a signature the holder verifies. The client's code identity alone cannot enroll, rotate, revoke, or change policy.

### Enrollment, policy, and protected pairing

Mutations are holder operations. The canonical bytes cover the operation, Mac id, policy, key ids, generations, public keys, fingerprints, nonce, and expiry. The holder verifies a signature over those bytes, re-reads the live generation under its lock, and commits with compare-and-swap. A workspace JSON file is not the policy and is not the enrollment record.

The Mac production key is one the holder created with the Secure Enclave token and `biometryCurrentSet`. The holder stores that public key. A carried file that says `secure-enclave` is not consulted. This is still not a third-party attestation that the key lives in hardware: the holder is trusting its own creation path. An imported public key cannot authorize a run.

Protected pairing, when a companion key is required:

1. The holder shows the Mac public-key fingerprint and a pairing nonce.
2. The iPhone creates its own key and shows that key's fingerprint.
3. A person compares the two screens. The software does not record that comparison unless both signature steps below finish.
4. The iPhone signs the pairing statement with Face ID: Mac id, both key ids, both fingerprints, nonce, expiry, and policy. The person carries that file. There is no relay and no listening server. Approval on the iPhone is not physical presence at the Mac.
5. The holder checks the signature against the public key inside the statement, shows both fingerprints again, and requires a new local Touch ID signature over the same statement before it stores the companion key.

Rotation of either key requires the current generation of that role. Switching away from dual, or from companion to local, requires both current factors, so a same-user client cannot downgrade the policy. Revocation increments the generation. Signatures from the old key fail that check. There is no user-writable reset. If the local key is gone, a new enrollment requires an administrator to remove holder state. That recovery is outside the same-user threat. A button that lets this user delete the holder directory would defeat guarantee (2).

### Input binding and crash recovery

The signed request binds run id, input fingerprints, contract fingerprint, workspace identity (volume id, directory inode, and path), Mac id, bounds, policy, nonce, expiry, and the local and companion key ids and generations. The holder reloads enrollment at consume. Expiry uses the holder's clock.

After the nonce is consumed and before the go byte, the holder copies the declared inputs and the contract to a root-owned `0444` snapshot and hashes those bytes. It also re-stats the workspace directory. Any mismatch kills the waiting wrapper, leaves the nonce consumed, and does not exec. A retry needs a new signature over the new bytes. Undeclared paths that the command opens later are not frozen. The holder enforces the timeout and the output cap.

Nonce states, each fsynced before the next side effect:

| State | Meaning | Recovery |
| --- | --- | --- |
| Consumed | Nonce reserved, no live pid | Do not spawn. The request is spent. |
| Armed | Wrapper pid and process start time recorded, go not sent | If that pid is still the waiting wrapper, kill it and do not exec. Do not spawn another. |
| Running | Go byte sent | If the pid is alive and the start time matches, adopt it and wait. Do not spawn another. |
| Reaped | Exit status stored | Do not spawn. |
| Unknown | Running record, but the pid is gone or the start time differs | Do not adopt a recycled pid. Do not spawn. The exit status may be lost. |

A crash after consume and before a durable pid does not launch. A crash after the go byte with a durable pid does not launch a second child. An already-running child is waited on. Replay of the nonce fails in every state above. That is the difference between a spent approval and a duplicate live execution.

The current `src/runspecimen/run.py` path still spawns under the workspace lease. That path stays until this holder exists. It is guarantee (1). `consumeForExecution` stays unwired. Wiring it to the workspace lease would describe guarantee (1) as guarantee (2).

Supported client: macOS 14.0 and later. The feasibility probes ran on macOS 27.0 as uid 501. An app update replaces the client. Holder state is outside the bundle and survives that update. Root can replace the holder, its directory, and the client. This design does not stop an administrator or root.

### Sandbox-to-daemon XPC, measured

The development app at `/private/tmp/rs-local-qa-provenance/DerivedData/Build/Products/Release/RunSpecimen.app` is signed `Apple Development: jahorka@gmail.com (PK6W7JVY6D)`, Team ID `UN6KF8636A`, bundle id `com.darashkevich.runspecimen`. Its entitlements are the Store set plus `com.apple.security.get-task-allow`. The Store set in `apps/macos/Entitlements/RunSpecimen.mas.entitlements` is sandbox, unsigned-executable memory, library validation disabled, user-selected files, and `network.client`. It has no app group and no `mach-lookup` exception.

On 2026-09-29 a throwaway app was signed with that Store entitlement file and the same development identity. A bare executable with those entitlements, started from a shell, exited 133 before `main`. The `.app` form launched. A temporary user LaunchAgent, not a root daemon, advertised `com.darashkevich.runspecimen.xpcprobe.listener`. An unsandboxed client signed with the same identity received `ok=holder`. The sandboxed app received `Connection invalid` for both a normal lookup and `XPC_CONNECTION_MACH_SERVICE_PRIVILEGED`. The agent was then removed. `launchctl` no longer finds it. No product daemon was installed, and the Store entitlements file was not edited.

`Connection invalid` with no listener is what both clients returned before the agent existed, so that string alone is not a sandbox proof. The difference appeared only while the service was running. This was a user-domain agent. It does not show that a root daemon's privileged service is reachable. Forum thread 802817: for App Store clients, publish the endpoint in an app group rather than adding `com.apple.security.temporary-exception.mach-lookup.global-name`. That app-group entitlement is not on this app. Adding it is an entitlement change and is not done here.

### Store distribution

Guideline 2.4.5, as published at <https://developer.apple.com/app-store/review/guidelines/>:

- (ii) a Mac App Store app is one self-contained bundle and cannot install code or resources in shared locations.
- (iii) it may not auto-launch at startup or login without consent, or leave a process running after the user quits, without consent.
- (iv) it may not download or install additional code to add functionality.
- (v) it may not request escalation to root or use setuid.
- (vii) updates come from the Mac App Store.

Putting a daemon outside the bundle does not satisfy those clauses. An external installer is the shared-location and extra-code case in (ii) and (iv), and a second update channel conflicts with (vii). `SMAppService.daemon` keeps the job inside the bundle, which avoids a second installer, and third-party writeups describe that job as root with a System Settings approval. This pass did not register one, so that root behavior was not re-measured. Even if the binary stays in the bundle, the design still asks for root, which is (v), and for a process that outlives the app, which is (iii) unless Apple treats the System Settings toggle as the consent that clause allows. Neither reading has been accepted for RunSpecimen. Review acceptance is not established.

If the holder is missing, the app fails closed. It does not fall back to a typed phrase.

## Smallest authorization still required

Authorize or refuse this expansion, and nothing wider: one embedded `SMAppService` launch daemon in the Mac App Store app, Team ID `UN6KF8636A`, running as root, owning holder state mode `0700`, spawning the signed wrapper as the console user, and publishing its Mach service only in one new app-group entitlement shared with `com.darashkevich.runspecimen`. No `com.apple.security.network.server`. No `com.apple.security.temporary-exception.mach-lookup.global-name`. No Endpoint Security. No separate installer. No Developer ID product beside the Store app.

If this is refused, guarantee (2) stays unimplemented on the Store channel. The app continues to enforce guarantee (1) only. A separate Developer ID product would be a different distribution channel and is not requested here.

These alternatives do not meet guarantee (2): the app container, a user-immutable flag, a keychain item the same user can delete, calling `consumeForExecution` on workspace files, and a daemon whose payload runs as the holder. `tests/test_lease.py` records the inode replacement against the current lease. That test passing means the workspace lease is still bypassable.

Until that holder exists, `consumeForExecution` stays unwired. The run path still asks for a typed phrase in a terminal. That phrase is the current guarantee (1) gate. It is not the biometric policy below, and it must not become a silent fallback once a biometric policy is required.

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
