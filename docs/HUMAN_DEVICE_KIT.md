# Human device kit

An agent must not run these steps. Do not pass `--human-invoked`. Do not tap Touch ID or Face ID. Do not grant a permission dialog. Do not type `APPROVE`. Do not pass `-allowProvisioningUpdates`, register a device, or read `~/.appstoreconnect/private_keys`.

The kit directory, when prepared, is `artifacts/human-device-kit/` next to the approved 0.1.4 (9) archive. It holds an unsigned iPhone build and the Mac diagnostic binary. Neither is installed. Neither is a Store package. Neither is this candidate. Diagnostic signing is not a bounded run. Phone approval is not physical presence at the Mac.

Candidate under review: the qafix2-pack successor of `5875c72b68746354e986a21f5d39f4b8e4bbdd1e`, which adds `artifacts/0.2.0rc15-2026-10-07-qafix2/`. Previous qafix pack `5875c72` (`artifacts/0.2.0rc15-2026-10-07-qafix/`, not overwritten). Previous bump pack `8015b6d` (`artifacts/0.2.0rc15-2026-10-06-bump/`, not overwritten). Previous docs-only pack `d42fe583dc3dd04e3cd3315f50608045c144d818` (`artifacts/rc15-2026-10-06-qualification-docfix/`, not overwritten). Previous package tree `fb05284d897d165b6fab9ad544ff9a1116675294` (`artifacts/rc15-2026-10-06-qualification/`, not overwritten). Parent `b3367ebeff76a1ed0c6fd6ecda2f613e5e8e93a4`. `main` remains `93f9b5708c1ba2d9b325ae2f9016d6a472fe6a20`. A merge to `main` is not a public release. Contracts with `execution_approval` of `local`, `companion`, or `dual` refuse a typed phrase. That refusal is not installed protection. Use [HUMAN-ACCEPTANCE.md](HUMAN-ACCEPTANCE.md) for the guarantee (1) session: brand-new venv from that wheel, `$VENV/bin/runspecimen` only, installed-bytes provenance abort, N10 protected-policy refusal, and a separate unknown-field schema check.

The two hashes below were built from `5c3957a3a8ddf9fceacc3096b2208ee7757e6b72`. Holder, iOS companion, and macOS core sources have changed since that commit. Since `1873f42`, iOS and macOS core sources changed; the kit hashes do not identify this candidate. Do not use them to qualify any channel.

| File | SHA-256 |
| --- | --- |
| `mac/RunSpecimenTouchIDDiagnostic` | `ee5f7733ed79a878d0983398f640ecea4cd11a7e53e6d3459636e808ae31374a` |
| `ios/RunSpecimenObserve.app/RunSpecimenObserve` | `4f38ee0adab75fa8db1d2b46b19168ed6810696e7b50cde8be437edadc374155` |

## Mac diagnostic

The binary in the kit is `RunSpecimenTouchIDDiagnostic`. From a checkout of this commit you can rebuild a Release binary, which does not include the test seams, with:

```sh
swift build --package-path apps/macos --product RunSpecimenTouchIDDiagnostic -c release
```

The binary is then `apps/macos/.build/release/RunSpecimenTouchIDDiagnostic`. There is no `rotate` command.

These two checks do not prompt. An agent may run them:

```sh
RunSpecimenTouchIDDiagnostic preview
RunSpecimenTouchIDDiagnostic enroll --directory /private/tmp/rs-touchid-diag --key-id diag-human
```

`preview` exits 0 and prints that it made no Secure Enclave call. `enroll` without `--human-invoked` exits 2.

Do not run `--human-invoked` to qualify this candidate. A Touch ID or Face ID press does not close E2 and does not admit an installed holder key. The commands that would prompt are not a supported acceptance workflow.

## iPhone provisioning is not acceptance

Signing and installing `RunSpecimenObserve` does not accept the iOS channel. The steps below are how a person would produce a signed build later. They are not a supported acceptance workflow for this candidate. A human H1 diagnostic session ran 2026-10-06 on an `ae6a071` Release build (not this SHA). It found IOS-H1-01 through IOS-H1-09, including IOS-H1-08 (the Mac pinned a revoked key as active) and IOS-H1-02 (Rotate/Revoke do not prompt Face ID despite the hints). It is diagnostic and defect evidence. It is not candidate qualification, and it is not E2 acceptance.

This Mac had no local provisioning profiles when the unsigned build was made. The agent did not create one.

1. Open `apps/ios/RunSpecimenObserve.xcodeproj` in Xcode on your Mac.
2. Select the scheme `RunSpecimenObserve`. Do not select `RunSpecimenObserveDev`. The dev scheme is the software signer and is not this test.
3. In Signing & Capabilities, select your team. Xcode's automatic signing will ask you to sign in. That login is yours. Do not hand the App Store Connect key to an agent.
4. Connect the iPhone, select it as the run destination, and press Run in Xcode. The first launch may ask the phone to trust the developer certificate. Accept that yourself.
5. The unsigned file `RunSpecimenObserve.app` in the kit is a Release iphoneos build of the shipping target (`com.darashkevich.runspecimen.observe`). It is not signed and was not installed. Use it only as the binary you can compare with the one Xcode installs. Installing still has to be the Xcode run above.

## iPhone hardware steps are blocked for this candidate

Do not enroll, sign, rotate, or revoke on the phone to qualify this candidate. A Face ID press is not installed holder admission and does not close E2. Carrying a package to the Mac is not a companion or dual run. A signature would show that a private key signed bytes. It would not show that protected holder state created that key.

## Supported acceptance: guarantee (1) only

Do this yourself, in a real terminal. An agent must not type the approval phrase, tap Touch ID or Face ID, or write that you did. Signing or installing the iPhone app is not this acceptance.

Pick one identity and write it down before you start. Do not mix them.

| Identity | What it is | What to record |
| --- | --- | --- |
| Published CLI | `0.2.0rc14` from PyPI or the GitHub Release | `runspecimen --version` and the published wheel or sdist hash you installed |
| This candidate | Unpublished `0.2.0rc15` from `artifacts/0.2.0rc15-2026-10-07-qafix2/` | Follow [HUMAN-ACCEPTANCE.md](HUMAN-ACCEPTANCE.md). Record `command -v runspecimen`, `$VENV/bin/runspecimen --version`, the provenance script JSON (installed RECORD vs wheel zip, plus `direct_url.json`), and the wheel SHA-256. Version strings are not proof. Do not invoke bare `runspecimen` or `python3` after the venv exists |

Copy the commands from [HUMAN-ACCEPTANCE.md](HUMAN-ACCEPTANCE.md). That sheet creates a brand-new venv in a fresh directory from the qafix2 wheel by absolute path, aborts if the venv target already exists, and invokes `$VENV/bin/runspecimen` only.

Expected: you approve in your terminal, then `preflight`, `run`, `postflight`, and `verify` for that campaign and run. `verify` exits 0. `verify` does not check HMAC or Ed25519 signatures.

Negatives:

- Closing the terminal without the phrase does not certify a run. There is no receipt to verify.
- N10: a contract that sets `execution_approval` to `local` refuses with `execution policy local has no typed-phrase fallback` before a prompt. That is not `contract contains unknown field(s): execution_approval`.
- Schema-rejection (not N10): a genuinely unknown field is refused as unknown.

Return: the provenance row from HUMAN-ACCEPTANCE.md, the campaign id, the run id, the `verify` exit status, the N10 refusal text, and the unknown-field refusal text.

## Blocked by E2 — do not run these

Installed local, companion, and dual flows are not supported on this candidate. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false. A root daemon cannot create the Secure Enclave key. Do not install, repair, or replace a holder. Do not notarize. Do not treat a biometric press, a carried phone package, or a second consume of a nonce as acceptance. Those steps are not waiting on you to exercise a working product.
