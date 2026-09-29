# Executor protection decision

Status: **not decided and not built.** No privileged helper, setuid binary, XPC service, Endpoint Security client, or new entitlement is in this candidate. `consumeForExecution` is not called by a run. `evaluateExecution` only calls a consume function a test supplies, and its `started` field stays false.

Three guarantees are different requirements. This note does not collapse them into one product, and it does not treat Endpoint Security as the only way to isolate a RunSpecimen resource.

## The three guarantees

1. **RunSpecimen's own transition.** The app and CLI refuse to approve, preflight, run, or postflight unless their own gate allows it. Today that gate is the terminal `APPROVE` phrase for a run, and an in-app confirmation for workflow writes. It binds the process that is RunSpecimen. It does not bind any other program.

2. **RunSpecimen's protected resources.** The execution lease is `fcntl` on `.runspecimen/execution.lock` inside the workspace (`src/runspecimen/lease.py`, `LEASE_FILENAME` in `src/runspecimen/paths.py`). Run state, the approval file, and certificates live in that same user-writable `.runspecimen` tree. The Mac app container is a separate sandbox. A same-user process that can write the workspace can replace those files. Moving the lease, the consumed-approval marker, and the enrollment snapshot into a location that other same-user processes cannot write — the app container, or a directory another OS access control limits to one holder — is resource isolation. It does not require Endpoint Security, and it does not stop the user from running the command with `/bin/sh`.

3. **Every equivalent command on the Mac.** Stopping every process from executing the same argv is global command blocking. That is a different product from (1) and from (2).

Owning a marker or a lease is (2) only for the files the owner can exclusively write. It is not (3). A root-owned marker stops a second `runspecimen` from restoring that file when the user cannot write it. The user can still exec a user-owned command.

## Options, with what each one actually covers

| Option | Guarantee it can support | What it does not do | Cost | Authorized |
| --- | --- | --- | --- | --- |
| Sandboxed Mac App Store app, as it is now | (1) for the app's own buttons and the CLI it launches. The container is the app's sandbox (Guideline 2.5.2). No `com.apple.security.network.server`. | A same-user process can write `.runspecimen` and can exec the command. | None beyond the current app. | This is the candidate. |
| Keep RunSpecimen state out of the user-writable workspace | (2) for the lease, marker, and enrollment snapshot, if those files move to the container or another directory the same user cannot rewrite. The workspace command and inputs stay where the user put them. | Does not stop `/bin/sh` from running the command. Root can still change the files. The CLI and the app would have to agree on the new location. | A design change to path layout. No new entitlement. Not implemented. | Not chosen. |
| Privileged helper (`SMJobBless`) holding those files | Still only (2), and only for files the helper exclusively owns. Apple's archived EvenBetterAuthorizationSample says Mac App Store apps may not use elevated privileges. Guideline 2.4.5(v) forbids root and setuid. Guideline 2.4.5(ii) and (iv) require one self-contained bundle. | Does not stop another process from exec of a user-owned command. Adds a Developer ID install and a second update channel. | Outside this Store app. | Not authorized. |
| Endpoint Security `ES_EVENT_TYPE_AUTH_EXEC` | (3), by denying execs. It requires the restricted entitlement `com.apple.developer.endpoint-security.client`. WWDC 2020 session 10159: the client is a system extension with a provisioning profile Apple grants separately. DTS forum 759149 (July 2024): that entitlement is not an App Store capability. | It is one way to block execs. It is not a way to protect the lease file, and it is not required for (1) or (2). Using it to block the user's own shell is global command blocking. | Restricted entitlement this team does not have. Cannot ship inside this Store app. | Not authorized. |

QA1773 requires every Mach-O in a sandboxed bundle to be sandboxed. WWDC 2023 session 10266: an XPC service inside `Contents/XPCServices` is replaced when the app is replaced. Neither fact selects among the three guarantees.

## Admin and root

Root can replace a helper, delete its files, and exec anything. An administrator who can install a helper can also run the command directly. Same-user automation and administrator or root compromise are different threats. No design in this document stops root.

A signature still does not prove the person understood the command. Hardware authentication protects the signing operation.

## What this candidate does

The sandboxed Store app covers guarantee (1) for its own process. Guarantee (2) is unfinished because the lease and run state remain in the user-writable workspace. Guarantee (3) is not this product. `evaluateExecution` does not spawn and it does not take the lease.

## The decision

Which guarantee should the next design be required to meet?

1. RunSpecimen will not perform its own run or workflow transition unless its own gate allows it.
2. Another same-user process cannot rewrite RunSpecimen's lease, consumed-approval marker, or enrollment snapshot. It may still run the user's command some other way.
3. No process on the Mac can run an equivalent command.

This review does not choose one, and it does not authorize a helper, a relay, Endpoint Security, or a new entitlement. Choosing (3) would be an explicit request for global command blocking. Choosing (2) would be an explicit request to relocate protected RunSpecimen state. Until then the candidate stays on (1), with (2) and (3) unfinished.

## What each choice would take

This is a plan for the decision. It does not start the work.

| If Yahor chooses | Implementation that would follow | What stays out |
| --- | --- | --- |
| (1) only | Keep the current app and CLI gates. Document that a same-user process can write `.runspecimen` and can exec the command. No path change. | No helper, relay, Endpoint Security client, or new entitlement. |
| (2) | Move the lease, the consumed-approval marker, and the enrollment snapshot out of the user-writable workspace into the app container, or another directory the same user cannot rewrite. The CLI and the app would have to read that location. The workspace command and inputs stay where the user put them. | Still no helper and no exec blocking. `/bin/sh` can run the command. |
| (3) | A separate product that can deny exec. That requires an entitlement this Store app cannot hold. It is not a change to the lease file. | It is not authorized, and it is not a substitute for (1) or (2). |

The candidate continues on (1) until one of those rows is chosen.
