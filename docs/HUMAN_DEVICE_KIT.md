# Human device kit

An agent must not run these steps. Do not pass `--human-invoked`. Do not tap Touch ID or Face ID. Do not grant a permission dialog. Do not type `APPROVE`. Do not pass `-allowProvisioningUpdates`, register a device, or read `~/.appstoreconnect/private_keys`.

The kit directory, when prepared, is `artifacts/human-device-kit/` next to the approved 0.1.4 (9) archive. It holds an unsigned iPhone build and the Mac diagnostic binary. Neither is installed. Neither is a Store package. Secure Enclave enroll, sign, revoke, and rotate are implemented and are not human-tested until you complete the prompts yourself.

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

A signature is evidence the hardware key signed those bytes after a biometric check. It is not evidence you understood a command, and it does not start a run. A run still requires you to type `APPROVE` yourself, and only after you have chosen which executor guarantee is required.
