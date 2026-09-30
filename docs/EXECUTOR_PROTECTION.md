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
| Embedded `SMAppService` root daemon plus an app-group Mach service | Could hold state only if Apple allowed a root helper. Guideline 2.4.5(v) prohibits that for a Mac App Store app. User approval does not change the sentence. | Not an established Store path. A measured sandboxed lookup with today's entitlements failed. | Would be root inside the Store app. | Not authorized. Not the decision being requested. |
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

Three different facts must not be collapsed. A person comparing two fingerprint strings is a human act this software does not observe. A valid signature proves possession of the matching private key. Neither fact is hardware provenance. A file, a fingerprint string, or a signature that says `secure-enclave` is not attestation.

Apple's Platform Security guide says `securityd` decides which keychain items a process may use from that process's keychain access groups and entitlements, and that a biometric ACL is evaluated in the Secure Enclave ([Keychain data protection](https://support.apple.com/guide/security/keychain-data-protection-secb0694df1a/web)). Apple's LocalAuthentication documentation says keychain services presents the biometric UI for the process that requests the item ([Accessing Keychain Items with Face ID or Touch ID](https://developer.apple.com/documentation/localauthentication/accessing-keychain-items-with-face-id-or-touch-id)). A root launch daemon is a different process from the signed GUI app, in the system domain rather than the console user's session. This repository has not shown that such a daemon can create a Secure Enclave key in the console user's data-protection keychain or present Touch ID or Face ID. That boundary is unproven. No enrollment path here calls `LAContext`.

Initial enrollment therefore stays in the user-session app until that boundary is proven. The same user can replace that app, so a public key the app submits is possession of whatever key the app holds, not a proof the Secure Enclave created it. The holder must not store that key as production hardware provenance. An imported public key cannot authorize a run.

Protected pairing, when a companion key is required:

1. The holder shows the Mac public-key fingerprint and a pairing nonce.
2. The iPhone creates its own key and shows that key's fingerprint.
3. A person compares the two screens. The software does not observe that comparison. The signatures below prove each key was used. They do not prove the person looked at both screens.
4. The iPhone signs the pairing statement with Face ID: Mac id, both key ids, both fingerprints, nonce, expiry, and policy. The person carries that file. There is no relay and no listening server. Approval on the iPhone is not physical presence at the Mac.
5. The holder checks the signature against the public key inside the statement, shows both fingerprints again, and requires a new local Touch ID signature over the same statement before it stores the companion key.

Rotation of either key requires the current generation of that role. Switching away from dual, or from companion to local, requires both current factors, so a same-user client cannot downgrade the policy. Revocation increments the generation. Signatures from the old key fail that check. There is no user-writable reset. If the local key is gone, a new enrollment requires an administrator to remove holder state. That recovery is outside the same-user threat. A button that lets this user delete the holder directory would defeat guarantee (2).

### Input binding

The signed request binds run id, input fingerprints, contract fingerprint, workspace identity (volume id, directory inode, and path), Mac id, bounds, policy, nonce, expiry, and the local and companion key ids and generations. The holder reloads enrollment at consume. Expiry uses the holder's clock.

Hashing a copy does not make the signed argv read that copy. `src/runspecimen/holder_protocol.py` `bind_execution` is the unprivileged statement of the mapping. `run.py` does not call it.

- The production binding requires a lowercase sha256 fingerprint for every executable, script, input, and dependency. A missing fingerprint, a value that is not 64 hex characters, or bytes that do not match that fingerprint fails closed. `fingerprints.get` returning nothing is not a binding.
- Every declared input, the executable, the script, and every declared dependency is opened with `O_NOFOLLOW`. A symlink at bind time fails closed. The copy is not a hard link.
- The destination name is the digest, and that name is not the check. The binder opens the destination with `O_NOFOLLOW`, requires a regular file, and hashes the bytes read from that fd. A precreated file, symlink, or directory at `files/<digest>` with different bytes or a different type fails closed. The corrupt entry is left in place and is not used. A short `write` is retried until the bytes are stored. If the write fails, the partial file is unlinked. If that unlink fails, the error says cleanup failed.
- `Snapshot.digest` is the hash of the bytes the fd reads. For an ordinary file that equals the signed fingerprint. For a script, the signed fingerprint is `source_digest` of the source bytes, and the fd reads the script after its shebang has been pointed at the snapshot interpreter. Those two digests differ. The script body after the shebang line is the signed body.
- The executable, the shebang interpreter, and that rebound script are mode `0555`. Other snapshot files are mode `0444`. A reused data file is not stripped of execute permission if another role already needed it.
- The executed argv is the signed argv with those paths replaced by snapshot paths. `argv[0]` is the snapshot of the executable and is executable. A declared input that is not an argv token fails closed, because exec would not be forced onto the snapshot. A live path left in argv fails closed.
- The working directory is a directory the binder creates for the snapshot. `cwd_mode` other than `snapshot` fails closed. The live workspace is not the cwd.
- Declared outputs are new regular files in a separate `outputs` directory, created with `O_NOFOLLOW | O_EXCL`. They are not the input inodes.
- A script whose shebang is `env` fails closed. A shebang interpreter that was not in the signed dependency set fails closed. A shebang interpreter that is a symlink fails closed, including `/bin/sh` on a host where that path is a symlink. An undeclared sibling file is not in the snapshot. The dynamic linker and system libraries are a residual: they are not snapshotted, and this design does not claim they are. A regular-file interpreter may itself name that system shell in its shebang. The kernel resolves that line. The binder does not treat that shell as a snapshot.
- After the snapshot fd is open, replacing or symlink-swapping the original path changes a later `stat` of that path and does not change the bytes behind the snapshot fd or the rewritten argv. `restat_agrees_with_snapshot` is a demonstration that a final stat can disagree. It is not the binding check.

`tests/test_holder_protocol.py` covers replacement, symlink rejection, a corrupt precreated destination, a matching reuse, missing and invalid fingerprints, short writes, cleanup failure, live cwd, an unbound interpreter, a distinct inode, an undeclared sibling, and a real unprivileged subprocess of the returned command.

### Launch handshake and crash recovery

The wrapper does not exec when it receives go. Go is only permission to ack. Exec happens only after the holder has fsynced an Acked record and then sent a commit byte. A crash that leaves Armed on disk therefore still has a wrapper that has not exec'd, and recovery kills that wrapper instead of committing. A crash after commit and before a durable Running record can leave Acked on disk while the process image is already the payload. Recovery adopts that pid when the start time matches. It does not send commit again and it does not spawn.

| Durable phase | What survived the crash | Recovery |
| --- | --- | --- |
| Consumed or intent | No pid | Nonce spent. Do not spawn. |
| Armed | Go may have been sent. Image is still the wrapper, because commit was not sent. | Kill the wrapper if the start time matches. Do not commit. Do not spawn. |
| Acked, image still wrapper | Commit was not sent. | Kill the wrapper. Do not commit on recovery. Do not spawn. |
| Acked, image already payload | Commit was sent and exec happened before Running was fsynced. | Adopt the pid. Do not commit again. Do not spawn. |
| Running, start time matches, a descendant is alive | Payload may have exited. | Supervise. Do not `waitpid` unless this process is the parent. Keep the lease. |
| Running, every recorded descendant is dead | Termination was observed without an exit status. | Lease may drop. The missing status is not success. Do not spawn the same nonce. |
| Start time differs | PID was reused. | Do not kill the new process. Do not adopt it. Phase becomes unknown. Keep the lease. Do not spawn. |
| Armed, acked, or running without pid and start | The in-memory record is partial. | Phase becomes unknown. Keep the lease. Do not spawn. `HolderSim` does not fsync this row. |

A restarted holder is not the parent of a surviving child. `foreign_wait` maps `ECHILD` to `echild`. That result is not an exit code. The lease stays while any recorded descendant with the original start time is alive, and while the phase is unknown. A second nonce cannot spawn until the lease drops. The same nonce cannot spawn again after consume.

`HolderSim` does not persist. `HolderSim.persists` is false, and its crash tests are not an fsync proof. `write_durable_record` writes a temp file, fsyncs it, renames it, and fsyncs the directory. `read_durable_record` returns none when the file is missing, and fails closed on an empty file, truncated JSON, or a symlink. `assess_durable` is the decision for a process that is not the parent: `spawn` is false and `wait` is `echild`. A missing record is not a launch and is not an exit status. A partial record keeps the lease and does not spawn. A phase that is not a string, including a list or an object, is partial and does not raise. A pid or start time must be an int greater than zero. A bool is not in that domain, and neither is a negative or zero value. The simulator uses the same phase and identity checks. Its result is still not an fsync proof. A complete armed record is not a commit. The simulator applies the same partial-record hold when its in-memory dict is missing those fields. That simulator result and the file result are separate tests.

Pipe EOF before ack or commit does not exec. `tests/test_holder_protocol.py` crashes the simulator after every step, and it checks EOF, PID reuse, a surviving descendant, a second nonce, partial records, fsynced files, and a real orphan `waitpid`. The orphan `waitpid` is the one real process in the crash tests. The step crashes are the simulator.

`tests/launch_fault_harness.py` is a separate disposable harness. It is not the simulator and `run.py` does not call it. A holder subprocess fsyncs a durable file and talks to a wrapper over pipes. `os._exit` at a named fault leaves the wrapper unreaped by that holder. The faults are before and after each consume, intent, armed, acked, and running fsync, and before and after go, ack, and commit. Wrapper EOF does not become a payload. A descendant that outlives the payload keeps the lease, so a second nonce does not spawn. After the recorded processes are gone, the missing status is not success, the same nonce stays spent, and a different nonce may proceed. Before fork, the harness fsyncs intent with `child` set to `uncertain` and keeps that lease until every recorded child is proven absent. A second nonce is not admitted while the child is alive, while its identity is missing, or while a lookup fails. Proving absence is a lookup that returns no process. That lookup is not a signal. `ps` `lstart` is second resolution and is not an identity token. Cleanup signals a pid only when a stored high-resolution start token matches a fresh lookup of that same pid. A pid-only file, a missing token, a mismatched token, or a lookup error is not signaled. A crash after the uncertain mark and before the identity file still holds the lease and has no pid to signal. A Linux zombie still has a ``/proc`` entry with the same start token; that state is terminated, not a live child, and it is not signaled again. ``ESRCH`` while reading that stat file means the pid is gone. It is not an unknown lookup. A permission error stays unknown and is not a signal. The missing status is not success. Corrupt or malformed `spent.json` is lost history. It is not an empty nonce set, and the harness does not replace it. A missing spent file is new state. `kill` and `ps` are not `waitpid` and they are not an exit status.

The current `src/runspecimen/run.py` path still spawns under the workspace lease. That path stays until this holder exists. It is guarantee (1). `consumeForExecution` stays unwired. Wiring it to the workspace lease would describe guarantee (1) as guarantee (2).

Supported client: macOS 14.0 and later. The feasibility probes ran on macOS 27.0 as uid 501. An app update replaces the client. Holder state is outside the bundle and survives that update. Root can replace the holder, its directory, and the client. This design does not stop an administrator or root.

### Sandbox-to-daemon XPC, measured

The development app at `/private/tmp/rs-local-qa-provenance/DerivedData/Build/Products/Release/RunSpecimen.app` is signed `Apple Development: jahorka@gmail.com (PK6W7JVY6D)`, Team ID `UN6KF8636A`, bundle id `com.darashkevich.runspecimen`. Its entitlements are the Store set plus `com.apple.security.get-task-allow`. The Store set in `apps/macos/Entitlements/RunSpecimen.mas.entitlements` is sandbox, unsigned-executable memory, library validation disabled, user-selected files, and `network.client`. It has no app group and no `mach-lookup` exception.

On 2026-09-29 a throwaway app was signed with that Store entitlement file and the same development identity. A bare executable with those entitlements, started from a shell, exited 133 before `main`. The `.app` form launched. A temporary user LaunchAgent, not a root daemon, advertised `com.darashkevich.runspecimen.xpcprobe.listener`. An unsandboxed client signed with the same identity received `ok=holder`. The sandboxed app received `Connection invalid` for both a normal lookup and `XPC_CONNECTION_MACH_SERVICE_PRIVILEGED`. The agent was then removed. `launchctl` no longer finds it. No product daemon was installed, and the Store entitlements file was not edited.

`Connection invalid` with no listener is what both clients returned before the agent existed, so that string alone is not a sandbox proof. The difference appeared only while the service was running. This was a user-domain agent. It does not show that a root daemon's privileged service is reachable. Forum thread 802817: for App Store clients, publish the endpoint in an app group rather than adding `com.apple.security.temporary-exception.mach-lookup.global-name`. That app-group entitlement is not on this app. Adding it is an entitlement change and is not done here.

### Store distribution

Guideline 2.4.5, fetched from <https://developer.apple.com/app-store/review/guidelines/> on 2026-09-30, says a Mac App Store app:

- (ii) is one self-contained bundle and cannot install code or resources in shared locations.
- (iii) may not auto-launch at startup or login without consent, or leave a process running after the user quits, without consent.
- (iv) may not download or install additional code to add functionality.
- (v) may not request escalation to root privileges or use setuid attributes.
- (vii) must take updates from the Mac App Store.

Clause (v) is a prohibition. A System Settings approval does not rewrite it, and embedding the helper with `SMAppService` does not rewrite it either. An embedded root daemon is not an established Mac App Store path for this app. A second installer for the same daemon is not Store-compatible either: that is (ii), (iv), and a second update channel under (vii). This pass did not register a daemon and did not add an entitlement.

If the holder is missing, the app fails closed. It does not fall back to a typed phrase.

## Decision, not a Store authorization

Guarantee (2) as specified needs a root holder that can `setuid` the payload to the console user. Guideline 2.4.5(v) forbids that inside a Mac App Store app. User consent does not close that conflict. Writing this section does not authorize a daemon, an entitlement, or a channel switch.

Yahor still wants guarantee (2). The Store build cannot implement it under the published rule. The later choice is one of these:

1. **Mac App Store only.** Guarantee (2) stays unimplemented. The shipping app enforces guarantee (1) only and does not claim (2).
2. **A separate Developer ID product**, authorized on its own, for the root holder and the client that talks to it. The Mac App Store app stays guarantee (1) and must not claim the Developer ID product's guarantee. That is a second channel, not a silent replacement of the Store app.
3. **Ask Apple before choosing.** The unsent question is `docs/APPLE_DTS_HOLDER_QUESTION.md`. Do not send it until Yahor says to.

These are not ways to get guarantee (2) on the Store channel: the app container, a user-immutable flag, a keychain item the same user can delete, calling `consumeForExecution` on workspace files, and a daemon whose payload runs as the holder. `tests/test_lease.py` records the inode replacement against the current lease. That test passing means the workspace lease is still bypassable.

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

A Mac App Store check of the final candidate is still required for the Store app. Passing it does not make guarantee (2) true, and guideline 2.4.5(v) means a root holder is not part of that Store app unless Apple says otherwise. The question in `docs/APPLE_DTS_HOLDER_QUESTION.md` has not been sent.
