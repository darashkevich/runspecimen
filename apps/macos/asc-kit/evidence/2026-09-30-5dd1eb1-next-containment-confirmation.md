# Next action-time containment / install confirmation (NOT performed)

Yahor’s broad “I approve everything” is **not** this confirmation and is **not**
QA sign-off. Do **not** replace the live holder until Yahor confirms the steps
below at action time.

## Still P1 on the live install
`/Applications/RunSpecimen Holder.app` remains user-writable Python under a
root launcher. This tip only ships source: isolated `holder_entry.py`,
drop-exec helper, readable `run-snapshots/`, Ed25519 device verify, full
mutation transactions, setsid-aware tree checks.

## Precise next confirmation Yahor must give before any live change
1. **Stop** the running system holder daemon via the registered label only
   (`launchctl bootout` / BTM), and confirm the socket is not serving.
2. **Replace** only `/Applications/RunSpecimen Holder.app` with a build whose
   MacOS binary execs `python -I …/Resources/Python/runspecimen/holder_entry.py`
   (no `-m`, no `RS_HOLDER_PYTHON`, no Homebrew, no `PYTHONPATH`).
3. **Install** root-owned module tree + optional embedded Runtime under
   Resources; create `/Library/Application Support/…/run-snapshots` mode `0755`
   and keep `state/` mode `0700`.
4. **Prove** as the console user: cannot write interpreter, `holder_entry.py`,
   `holder_daemon.py`, or any path component; no symlinks; ACLs do not grant
   write.
5. **Restart** only after that proof. Privileged acceptance is a separate gate.
6. Out of scope unless separately confirmed: `/Applications/RunSpecimen.app`,
   notarization, ASC submit, merge, publish.

## Explicit non-actions for this agent pass
No modify/replace/codesign/uninstall/restart/signal of either app; no live
root socket exercise; no credentials/biometrics; no APPROVE.
