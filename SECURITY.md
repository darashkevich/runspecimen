# Security policy

RunSpecimen is an orchestration and evidence layer, not an operating-system
sandbox. Treat the executed payload as fully trusted code with the same access
as the invoking user.

For a suspected vulnerability, do not include secrets, private receipts, or
proprietary contracts in a public report. Provide a minimal reproduction, the
RunSpecimen version, Python version, operating system, and the relevant command.
Until a private reporting address is published, keep the report private to the
maintainers of the distribution from which you received RunSpecimen.

Security fixes are supported for the latest release candidate and latest stable
release. Hash-chain verification detects modification; it does not prevent a
privileged attacker from replacing an entire local history.
