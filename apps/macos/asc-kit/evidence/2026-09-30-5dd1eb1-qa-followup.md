# QA follow-up evidence — after 5dd1eb1

Unprivileged source/tests only. **Green CI is not production sign-off.**
Installed daemon and `/Applications/RunSpecimen*.app` were **not** modified.
`/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`.

## Source fixes
- Isolated `holder_entry.py` path execution; no `-m` / post-import `RS_HOLDER_MODULE_ROOT` discovery.
- Drop-exec helper (no `preexec_fn` in threaded daemon); refuse UID 0; fail closed on setgroups.
- Payload snapshots under `run-snapshots/` outside 0700 state.
- Setsid-aware pid-tree check before lease release.
- Ed25519 device signatures for local/companion/dual (not SE; labeled not-hardware).
- All protected mutations under `_transaction()`; runtime chain verified before load.

## Tests
Focused holder/protocol: 53 OK. Do not prove installed protection. No live root socket.

## GUI
Existing development app only (`91081f5`, main `cfb41bcc…`). Container backup/restore.
About Escape, Reviewer Demo, Validate. No APPROVE. No Holder.app/root daemon.
