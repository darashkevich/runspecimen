# Candidate manifest

This file describes the unpublished integrated candidate. It does not publish, upload, or replace anything.

| Item | Identity |
| --- | --- |
| Engine / package | `0.2.0rc15` in `src/runspecimen/__init__.py` and `pyproject.toml` |
| Plugin | `0.2.0-rc.15` |
| Status | Not tagged, not on PyPI, not on the Homebrew tap |
| Published engine, unchanged | `0.2.0rc14` / `v0.2.0-rc.14`, tag peel `25f4013c5c84b89b24024182f7c308dcffe084b4` |
| Published wheel SHA-256 | `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948` |
| Published sdist SHA-256 | `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3` |
| Published plugin zip SHA-256 | `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` |
| Approved Mac app, unchanged | **0.1.4 (9)**, build `51a18894-02e3-4846-86f5-29cc345567f0`, `READY_FOR_SALE` |
| Approved package SHA-256 | `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d` |
| Proposed app update | **0.1.6 (1)**, stable track only. Not agreed. Not exported. |
| App version string in the project | still **0.1.5 (13)** until that proposal is accepted |

The exact git commit is the commit that introduces this manifest on `cursor/integrated-release-candidate`.

## Tracks

| Track | In this candidate | In a stable-only 0.1.6 (1) store binary, only if Yahor agrees |
| --- | --- | --- |
| Capture, plain-text and version failure reporting | yes | yes |
| Nested secret stripping, receipts, About and Settings close | yes | yes |
| Fast path | yes | yes |
| Local biometric prototype | yes, not an execution gate | exclude the prototype sources and test hooks, then verify the binary |
| Companion transport | user-mediated RSBA2 package. The Mac pin ignores a carried file's Secure Enclave label. Phone buttons call Secure Enclave directly. No socket or relay | not built |
| Privileged helper, relay, `network.server` | not added. The sandboxed app does not meet the stronger same-user requirement. The open question is in `docs/EXECUTOR_PROTECTION.md` | not added |

`ProductionPolicy.accepts` is a test classifier. It does not enforce a biometric execution policy.
