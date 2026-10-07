# Installed holder socket mode (RS-07)

Status: **investigate only.** This note does not change `os.chmod(sock_path, 0o666)` in `src/runspecimen/holder_daemon.py`. E2 stays open. `run_integration_complete` stays false. Installed Secure Enclave / biometric admission stays fail-closed.

The installed daemon binds `holder.sock` under `/Library/Application Support/com.darashkevich.runspecimen.holder/` and sets mode `0666`. Callers are authenticated after accept with kernel peer credentials (`getpeereid` / `SO_PEERCRED` / Darwin `LOCAL_PEERCRED`) plus an HMAC over the framed message (`message_mac` in `src/runspecimen/execution_holder.py`). The unprivileged test adapter uses mode `0600` on a temp socket; that is not the installed daemon.

## Threat model

Attacker in scope for this note: another local account on the same Mac, and any process that can open a UNIX-domain socket. Same-user automation (another process as the console user) is the guarantee-(2) attacker in `docs/EXECUTOR_PROTECTION.md`. Root and kernel remain out of scope, as elsewhere.

| Control | What it does | What it does not do |
| --- | --- | --- |
| Directory `0755`, root-owned support path | Another user cannot replace `holder.sock` if they cannot write the directory. `assert_support_before_secret` refuses a non-sticky world-writable ancestor. | Does not stop connect. Does not stop root. |
| Socket mode `0666` | Any local uid can `connect(2)`. | Not authentication. |
| `getpeereid` (and Linux/Darwin fallbacks) | The daemon stamps the kernel uid/gid of the connecting process. A client-supplied uid is not the peer. Consume/execute use that peer to choose the payload identity. | Does not stop a same-user process. Does not stop connect. Unavailable peer identity fails closed. |
| Message MAC | A caller secret is required to seal a request. Bootstrap is limited to enroll and pair. | A leaked secret plus a connect from that uid is a valid caller. The MAC is HMAC, not a signature. |
| Admission gate | Caps in-flight connections. | A noisy local account can still occupy slots. |

Residual with `0666`: any local account can connect, send junk, read error strings, and consume admission slots. They cannot forge a MAC without a caller secret. They cannot pretend to be another uid: the kernel peer is the connecting process. Same-user malware already has the console user's uid, so mode bits do not separate it from the GUI app.

## Is `0660` plus a group feasible on macOS for the app/holder pair?

A dedicated group (for example `_runspecimen_holder`) with socket `0660` `root:_runspecimen_holder` would block other local accounts from `connect(2)`. That is a real multi-user hardening. It is not a same-user control.

Feasibility for the **Developer ID** app and a **root** holder daemon:

- The installer can create the group and add the installing user (`dseditgroup`). Root can always connect.
- The GUI app then needs that supplementary group at launch. LaunchServices / `launchd` Aqua jobs inherit Open Directory groups for that user. Other processes of that user inherit them too, so the same-user attacker still connects.
- The sandboxed Mac App Store app must not depend on this socket. Guideline 2.4.5(v) and `docs/EXECUTOR_PROTECTION.md` keep the Store product on guarantee (1). A posix group does not give a sandboxed Store client a supported path into a root daemon in `/Library/Application Support`.
- App groups (`$(TeamIdentifier).…`) are a sandbox container mechanism, not a substitute for the socket's posix mode. Mixing them with `0660` does not make Store-to-daemon IPC allowed.

Unproven without a human install: whether a sandboxed client, if someone later tried to point it at this socket, would be allowed to connect even with group membership. That experiment is not authorized here.

## Recommendation

Keep mode `0666` for this tree. Do not change the permission in this PR.

Reasons:

1. Authentication is already `getpeereid` + message MAC. Mode `0666` is the connect filter, not the trust boundary.
2. `0660` + a group does not close the same-user case that guarantee (2) cares about.
3. The group story is installer and identity work for a daemon that is still not the shipping Store app. Changing the mode now would imply a pairing that is not proven.
4. A later Developer ID installer can add `0660` + `_runspecimen_holder` as extra filtering against other local accounts, after the app and daemon's posix identities are measured. That change should land with tests for connect-from-other-uid refused and connect-from-group allowed, without treating those tests as installed protection.

If a future change tightens the mode, keep fail-closed peer identity and the MAC. Do not treat a quieter socket as E2 closed, as biometric admission, or as a reason to accept a typed phrase.
