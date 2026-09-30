# Implementation handoff — QA a2fcab0 follow-up

Tip after this pass will be recorded in the commit and release artifacts. This document is not production sign-off. Green CI is not production sign-off. The installed `/Applications/RunSpecimen Holder.app` and its root daemon were **not** modified, restarted, signaled, or exercised in this pass. `/Applications/RunSpecimen.app` was not touched.

## P1 containment / repair plan (awaits Yahor's approval)

Independent QA showed the installed Holder.app tree is user-owned (`yahor`, `0755`) and `Resources/Python/runspecimen/*.py` is user-writable (`0644`). The native root launcher sets `PYTHONPATH` into that tree and execs an external Python `-m`. Bundle signing does not authenticate each import. That fails the intended same-user protection.

**Do not continue privileged acceptance against the current install.**

When Yahor later authorizes a repair (separate install approval), the target design is:

1. A **protected isolated runtime** owned by `root`, with the interpreter binary, standard library, and holder module tree all **root-owned**.
2. Every path in that trust chain (binary, `lib`, holder package, parent directories) **mode-checked** (not group/world-writable) and **symlink-checked** (`O_NOFOLLOW` / refuse symlink components) before exec and before import.
3. **No** loading holder code from a user-writable tree, from a caller-controlled `PYTHONPATH`, from Homebrew, or from a user-selected `RS_HOLDER_PYTHON`.
4. Prefer an embedded interpreter shipped inside a root-owned payload, or `/usr/bin/python3` only after the same ownership/mode/symlink verification of every resolved module path used for `-m runspecimen.holder_daemon`.
5. After install, re-verify with an independent QA pass that a same-user write to the runtime tree is impossible without privilege escalation.

This pass only fixed the **unprivileged** core/adapter/daemon *source* (framing, verifier, holder-owned execute). It does **not** implement the install repair and does **not** change the live app.

## What this pass fixed (unprivileged)

- Bounded AF_UNIX framing, read timeouts, admission limits, malformed-frame handling (`holder_io.py` + adapter + daemon source). Tests use the unprivileged adapter only.
- Cryptographic device-HMAC verifier for `local` / `companion` / `dual`, plus authenticated `bootstrap` enroll/pair distinct from human authorization. Software-test-double remains only when the adapter is constructed with `allow_test_double=True` and stays labeled not-hardware. Imported `secure-enclave` labels stay unverified.
- Holder-owned `execute`: spawn, supervision, and lease release only after verified termination. Client `note-absent` cannot clear a lease. Client does not `Popen` held policies.
- Workspace executables are not exempted via `live_executable`. Declared reads are snapshotted. Mutation-after-consume covered by execute-from-snapshot tests.
- Durable write lock + strict schema refusal for known holder records.
- Tests state they do not prove installed protection.

## Remaining human / security gates

- Yahor must approve and authorize any Holder.app reinstall that implements the protected runtime plan above before further privileged acceptance.
- Genuine Mac + iPhone biometric pairing/local/companion/dual/run/replay still require Yahor's hardware prompts (`--human-invoked`, Face ID on device). Agent will not run them.
- iPhone `RunSpecimenObserve` remains unsigned until Yahor signs it in Xcode.
- Store channel and guarantee (1) Store app are unchanged. Guarantee (2) is not claimed for the live install.
- No notarize, merge, publish, or Apple submission in this pass.

## Development GUI session (this pass)

Used existing development app only: `/private/tmp/rs-local-qa-91081f5/DerivedData/Build/Products/Release/RunSpecimen.app` (Apple Development, Team UN6KF8636A). Shared container backed up to `/private/tmp/rs-qa-a2fcab0-container-backup-*`, app launched, QA pid quit only, container restored. Fixture `/private/tmp/rs-qa-91081f5-receipts/workspace` was present. Compare / diff / retain were **not** finished in the GUI in this pass (not automated without APPROVE/biometrics). Prior finished receipt evidence on source `91081f5` remains on file. No APPROVE. No biometric run. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`. Installed Holder.app was not modified.

## Channel / version matrix (candidate tip)

| Channel | Identity | Status |
| --- | --- | --- |
| Integrated candidate git tip | 034d9376bd8b5d99f10bb5eef9be3202b9a2b73e | Unpublished; PR #39 branch `cursor/integrated-release-candidate` |
| Engine label | `0.2.0rc15` | Candidate only; must not overwrite published rc14 |
| Wheel / sdist / plugin | See `artifacts/rc15-2026-09-30-qa-followup/SHA256SUMS` after release_check | New dir; prior artifact dirs not overwritten |
| Mac App Store app | `/Applications/RunSpecimen.app` mtime `2026-09-26 13:56:03` | Untouched this pass |
| Developer ID Holder install | `/Applications/RunSpecimen Holder.app` user-owned; root daemon still running from prior install | **Not modified**; privileged acceptance stopped pending protected-runtime repair |
| PyPI / Homebrew / GitHub Release | Public still **0.2.0rc14** | Not published from this tip |
| iOS Observe | Unsigned kit / Xcode sign pending Yahor | Not Store |

Green CI is not production sign-off.

## Human Mac + iPhone instructions (final tip)

Do not ask an agent to run these. Do not type `APPROVE` as a biometric substitute.

```bash
# Worktree tip after this commit (SHA in git log / evidence)
cd /Users/yahor/Documents/Codex/2026-08-24/qa-worktrees/pr39-protocol
DIAG=artifacts/human-device-kit/mac/RunSpecimenTouchIDDiagnostic
# Expected kit binary SHA-256 (from docs/HUMAN_DEVICE_KIT.md):
# ee5f7733ed79a878d0983398f640ecea4cd11a7e53e6d3459636e808ae31374a
DIR=/private/tmp/rs-touchid-diag
KEY=diag-human
"$DIAG" preview
"$DIAG" enroll --directory "$DIR" --key-id "$KEY"   # expect exit 2 without --human-invoked
"$DIAG" --human-invoked --directory "$DIR" --key-id "$KEY" enroll
"$DIAG" --human-invoked --directory "$DIR" --key-id "$KEY" sign
"$DIAG" --human-invoked --directory "$DIR" --key-id "$KEY" cancel
"$DIAG" --human-invoked --directory "$DIR" --key-id "$KEY" revoke
```

iPhone: open `apps/ios/RunSpecimenObserve.xcodeproj`, scheme **RunSpecimenObserve** (not Dev), sign with your team in Xcode, install on device. Enroll / cancel / rotate / sign / revoke on device. Carry pairing material to Mac. Then, after Holder runtime repair is approved and installed: one local, one companion, one dual held run, then rejected replay. Until the protected-runtime repair ships, do not treat the live Holder.app as guarantee (2).
