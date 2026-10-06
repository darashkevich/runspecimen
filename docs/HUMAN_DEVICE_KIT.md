# Human device kit

An agent must not run these steps. Do not pass `--human-invoked`. Do not tap Touch ID or Face ID. Do not grant a permission dialog. Do not type `APPROVE`. Do not pass `-allowProvisioningUpdates`, register a device, or read `~/.appstoreconnect/private_keys`.

The kit directory, when prepared, is `artifacts/human-device-kit/` next to the approved 0.1.4 (9) archive. It holds an unsigned iPhone build and the Mac diagnostic binary. Neither is installed. Neither is a Store package. Neither is this candidate. Diagnostic signing is not a bounded run. Phone approval is not physical presence at the Mac.

Candidate under review: `fb05284d897d165b6fab9ad544ff9a1116675294`, which adds `artifacts/rc15-2026-10-06-qualification/`. Parent `b3367ebeff76a1ed0c6fd6ecda2f613e5e8e93a4`, on `cursor/evidence-expansion-coherence`. `main` remains `93f9b5708c1ba2d9b325ae2f9016d6a472fe6a20`. A merge to `main` is not a public release. Contracts with `execution_approval` of `local`, `companion`, or `dual` refuse a typed phrase. That refusal is not installed protection.

The two hashes below were built from `5c3957a3a8ddf9fceacc3096b2208ee7757e6b72`. Holder, iOS companion, and macOS core sources have changed since that commit. Those hashes are not this candidate. Do not use them to qualify any channel.

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

Signing and installing `RunSpecimenObserve` does not accept the iOS channel. The steps below are how a person would produce a signed build later. They are not a supported acceptance workflow for this candidate, and they were not run on 2026-10-06.

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
| This candidate | Unpublished `0.2.0rc15` from `artifacts/rc15-2026-10-06-qualification/` | `git rev-parse HEAD`, `runspecimen --version`, and the wheel and sdist hashes in that directory's `SHA256SUMS` |

Prerequisites: an ordinary contract with no `execution_approval` field, a disposable workspace, and a harmless bounded command. `doctor`, `validate`, and `status` should exit 0 before you approve.

Expected: you approve in your terminal, then `preflight`, `run`, `postflight`, and `verify` for that campaign and run. `verify` exits 0.

Negatives:

- Closing the terminal without the phrase does not certify a run. There is no receipt to verify.
- A contract that sets `execution_approval` to `local`, `companion`, or `dual` refuses the phrase before a prompt. That refusal is expected. It is not a successful protected run.

Return: the identity row you recorded, the campaign id, the run id, the `verify` exit status, and whether the phrase-refusal negative exited before a prompt.

## Blocked by E2 — do not run these

Installed local, companion, and dual flows are not supported on this candidate. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false. A root daemon cannot create the Secure Enclave key. Do not install, repair, or replace a holder. Do not notarize. Do not treat a biometric press, a carried phone package, or a second consume of a nonce as acceptance. Those steps are not waiting on you to exercise a working product.
