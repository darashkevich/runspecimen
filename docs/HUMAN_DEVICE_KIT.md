# Human device kit

An agent must not run these steps. Do not pass `--human-invoked`. Do not tap Touch ID or Face ID. Do not grant a permission dialog. Do not type `APPROVE`. Do not pass `-allowProvisioningUpdates`, register a device, or read `~/.appstoreconnect/private_keys`.

The kit directory, when prepared, is `artifacts/human-device-kit/` next to the approved 0.1.4 (9) archive. It holds an unsigned iPhone build and the Mac diagnostic binary. Neither is installed. Neither is a Store package. Secure Enclave enroll, sign, revoke, and rotate are implemented and are not human-tested until you complete the prompts yourself. Diagnostic signing is not a bounded run. The chosen run policy is local Touch ID, an explicitly selected paired iPhone, or both devices. Phone approval is not physical presence at the Mac.

Tip for these instructions: the commit that contains this file on `cursor/evidence-expansion-coherence` (lineage #39/`e2a3216`, #47/`329e08b`, #49/`18ef461`). `cursor/integrated-release-candidate` is historical at `a0dc233`. Holder fail-closed code at parent `1873f420888397f7f4e5d496d3f8daae80bc15c3` is unchanged by this docs pass. Contracts with `execution_approval` of `local`, `companion`, or `dual` fail closed without the holder and refuse a typed phrase. That path is the unprivileged adapter and core only. It is not installed protection, not Touch ID, and not a paired phone. A software test double stays labeled as not hardware. An imported Secure Enclave label is not attestation. Administrator or root can still defeat a user-level holder.

These binaries were built from `5c3957a3a8ddf9fceacc3096b2208ee7757e6b72`. Swift, iOS, and macOS product sources are unchanged from that commit through the tip that contains this file, so the kit was not rebuilt. Check the hashes before you run anything that can prompt.

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

You run the rest yourself. Each command passes `--human-invoked`, `--directory /private/tmp/rs-touchid-diag` (or a directory inside it), and `--key-id diag-...` of at most 64 characters. Read the printed request before you authenticate.

```sh
DIR=/private/tmp/rs-touchid-diag
KEY=diag-human
RunSpecimenTouchIDDiagnostic --human-invoked --directory "$DIR" --key-id "$KEY" enroll
RunSpecimenTouchIDDiagnostic --human-invoked --directory "$DIR" --key-id "$KEY" sign
RunSpecimenTouchIDDiagnostic --human-invoked --directory "$DIR" --key-id "$KEY" reload
RunSpecimenTouchIDDiagnostic --human-invoked --directory "$DIR" --key-id "$KEY" cancel
RunSpecimenTouchIDDiagnostic --human-invoked --directory "$DIR" --key-id "$KEY" revoke
```

`sign` and `reload` print the request and then the signature. `cancel` asks you to cancel the prompt; a signature from that command is a failed cancel. `revoke` prints `revoked`. A later `sign` must not produce a signature.

## iPhone provisioning

This Mac had no local provisioning profiles when the unsigned build was made. The agent did not create one.

1. Open `apps/ios/RunSpecimenObserve.xcodeproj` in Xcode on your Mac.
2. Select the scheme `RunSpecimenObserve`. Do not select `RunSpecimenObserveDev`. The dev scheme is the software signer and is not this test.
3. In Signing & Capabilities, select your team. Xcode's automatic signing will ask you to sign in. That login is yours. Do not hand the App Store Connect key to an agent.
4. Connect the iPhone, select it as the run destination, and press Run in Xcode. The first launch may ask the phone to trust the developer certificate. Accept that yourself.
5. The unsigned file `RunSpecimenObserve.app` in the kit is a Release iphoneos build of the shipping target (`com.darashkevich.runspecimen.observe`). It is not signed and was not installed. Use it only as the binary you can compare with the one Xcode installs. Installing still has to be the Xcode run above.

## On the iPhone, after you have installed that signed build

Use the shipping scheme, not `RunSpecimenObserveDev`. The buttons are on the companion hardware screen. There is no command-line enroll on the phone.

1. Tap **Enroll this iPhone**. The Face ID prompt is the Secure Enclave access control (`biometryCurrentSet` and `privateKeyUsage`). Cancel once and confirm no pairing file is offered as a new active key.
2. Tap **Enroll this iPhone** again and answer Face ID. Then tap **Rotate to the replacement key** and answer Face ID for the new key.
3. Paste the carried package, tap **Show request**, and read the lines. Tap **Sign with Face ID** only after they match the package you mean.
4. Edit the package after Show request. **Sign with Face ID** stays disabled until you tap **Show request** again.
5. Tap **Revoke this iPhone key**. A later **Sign with Face ID** must not produce a signature.
6. Carry the pairing JSON to the Mac and pin it in Workflows. The status must say the Secure Enclave label was not accepted.

A Release build of the phone app does not contain `beforeFinalSignatureDecision`. A Debug run from Xcode does, because that is the build the unit tests host. Use Release for the human check.

A signature is evidence the matching private key signed those bytes. It is not evidence you compared the fingerprints on the two screens, and it is not evidence the key was created in a Secure Enclave. Those are three separate claims. It is not evidence you understood a command, and it does not start a run. The 0.1.5 (13) GUI report for source `ea21a7fa17140dc15dab74493d384b2a8b7a150c` and engine rc14 is a different build. It does not accept this kit. `runspecimen run` still asks for a typed phrase. That phrase is guarantee (1). It is not local Touch ID, paired-iPhone approval, or dual approval, and it must not be used as a substitute for those once they are required.

## Human acceptance session

Do this yourself. An agent must not tap Touch ID or Face ID, type the approval phrase, or write that you did.

The binaries above are still the `5c3957a` diagnostic and the unsigned iPhone build. They can exercise hardware signing. They cannot exercise a bounded run under installed guarantee (2): the holder is not installed, launchd/`SMAppService` was not registered, and these kit binaries are not the development GUI. Diagnostic signing is not execution acceptance.

What you can check now, on these binaries:

1. Mac: `preview`, then `enroll` without `--human-invoked` (expect exit 2). Then the `--human-invoked` enroll, sign, cancel, and revoke commands in the Mac section. Cancel must not produce a signature. A later sign after revoke must not produce a signature.
2. iPhone: install a Release build of `RunSpecimenObserve` by the Xcode steps above. Enroll, cancel once, enroll again, rotate, sign, edit-after-show, and revoke. Carry the file to the Mac and pin it. The Mac must not treat a file's Secure Enclave label as hardware provenance.
3. Quit and reopen the diagnostic directory. A revoked key must stay revoked.

What waits until the holder in `docs/EXECUTOR_PROTECTION.md` is authorized and actually built:

4. Protected pairing: compare the Mac fingerprint and the iPhone fingerprint on the two screens, then complete both signatures. Carried file only.
5. One policy at a time: local Touch ID, then explicitly selected paired iPhone, then dual. Each must fail closed if you cancel. None may fall through to a typed phrase.
6. One harmless bounded command in a disposable workspace, after you have read the request. Then repeat the same request and confirm the replay is rejected. Check the receipt for that run yourself.

Both devices need those later steps if both ship. Completing only the diagnostic list is not that session.
