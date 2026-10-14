# Smallest remaining human Mac+iPhone steps (do not run in agent pass)

Not biometric completion by an agent. No `--human-invoked`, Touch ID, Face ID,
or APPROVE from automation. Tip: record the SHA that lands on
`cursor/integrated-release-candidate` after this follow-up.

1. **Pair (Mac):** enroll + pair Mac with bootstrap (enroll/pair only); store the
   returned Ed25519 private key offline; confirm attestation is
   `device-ed25519-not-hardware` (not Secure Enclave).
2. **Pair (iPhone):** pair phone role the same way; keep private key on device
   custody only.
3. **Local:** set policy `local`; human signs the exact challenge bytes
   (payload digest, launch_argv, bounds, mutation_digest); consume once; execute
   once; replay refuses.
4. **Companion:** policy `companion`; phone signs the same exact bytes; Mac-only
   signature must fail closed.
5. **Dual:** both signatures required; omit either → refuse; revoke either device
   → refuse.
6. **Run/replay:** one successful run per nonce; mutate input after consume →
   refuse; client note-absent cannot clear lease.

Stop if live Holder.app has not received a separate action-time containment
confirmation. Green CI is not production sign-off.
