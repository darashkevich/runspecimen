# Human Mac + iPhone pairing / local / companion / dual / run / replay

**Do not run these steps in this pass.** Prepared for Yahor only. No
`--human-invoked`, no Touch ID, no Face ID, no APPROVE from an agent.

Prerequisite tip: the SHA that lands on `cursor/integrated-release-candidate`
after this follow-up (record exact SHA in the handoff). Unprivileged tests are
not installed protection. Live Holder.app repair must already be authorized and
applied if privileged acceptance is intended; otherwise stay on the
development/unprivileged path and stop before any root socket.

## A. Local (Mac only)

1. Enroll the Mac device under policy `local` with a real LocalAuthentication
   prompt (Touch ID / password as configured). Do not use the software test
   double.
2. Consume with a fresh nonce; confirm expiry is checked at consume time.
3. Execute once; confirm launch matches the signed binding only.
4. Replay the same nonce; expect refuse.
5. Mutate a bound input after consume; expect refuse before spawn.

## B. Companion (paired iPhone)

1. Pair iPhone Observe/companion with bootstrap scoped to enroll/pair only.
2. Confirm bootstrap cannot authorize consume/execute.
3. Approve a consume challenge on the phone that covers exact payload digest,
   launch_argv, bounds, and mutation digest bytes (not a label).
4. Run once; replay must fail.

## C. Dual

1. Require both Mac local and paired iPhone signatures on the same authorized
   challenge bytes.
2. Omit either factor; consume/execute must fail closed.
3. Successful dual run once; replay fails; revoke either device and confirm
   fail-closed.

## D. Evidence to keep

- Exact tip SHA, app/engine hashes, policy, device fingerprints (not secrets).
- Screenshots or timestamps of biometric prompts (human-captured).
- Spent nonce + refused replay log lines.
- Explicit note: device-HMAC test doubles are not hardware; green CI is not
  production sign-off; installed daemon was not modified in the agent pass.
