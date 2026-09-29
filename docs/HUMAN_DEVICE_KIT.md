# Human device kit

An agent must not run these steps. Do not pass `--human-invoked`. Do not tap Touch ID or Face ID. Do not grant a permission dialog. Do not type `APPROVE`. Do not pass `-allowProvisioningUpdates`, register a device, or read `~/.appstoreconnect/private_keys`.

The kit directory, when prepared, is `artifacts/human-device-kit/` next to the approved 0.1.4 (9) archive. It holds an unsigned iPhone build and the Mac diagnostic binary. Neither is installed. Neither is a Store package. Secure Enclave enroll, sign, revoke, and rotate are implemented and are not human-tested until you complete the prompts yourself.

## Mac diagnostic

The binary in the kit is `RunSpecimenTouchIDDiagnostic`. From a checkout of this commit you can rebuild it with:

```sh
swift build --package-path apps/macos --product RunSpecimenTouchIDDiagnostic
```

1. Run `RunSpecimenTouchIDDiagnostic preview` with no `--human-invoked`. It should exit 0 and must not prompt.
2. Run `enroll`, `sign`, and `revoke` yourself. Pass `--human-invoked`, `--directory` under `/private/tmp/rs-touchid-diag`, and a key id that starts with `diag-`. There is no `rotate` command in this diagnostic.
3. Read the printed request and confirm it matches the bytes you intend to sign before you authenticate.
4. Cancel one prompt and confirm no signature is printed.

`enroll` without `--human-invoked` exits 2 and does not call Secure Enclave. That check is not a hardware test.

## iPhone provisioning

This Mac had no local provisioning profiles when the unsigned build was made. The agent did not create one.

1. Open `apps/ios/RunSpecimenObserve.xcodeproj` in Xcode on your Mac.
2. Select the scheme `RunSpecimenObserve`. Do not select `RunSpecimenObserveDev`. The dev scheme is the software signer and is not this test.
3. In Signing & Capabilities, select your team. Xcode's automatic signing will ask you to sign in. That login is yours. Do not hand the App Store Connect key to an agent.
4. Connect the iPhone, select it as the run destination, and press Run in Xcode. The first launch may ask the phone to trust the developer certificate. Accept that yourself.
5. The unsigned file `RunSpecimenObserve.app` in the kit is a Release iphoneos build of the shipping target (`com.darashkevich.runspecimen.observe`). It is not signed and was not installed. Use it only as the binary you can compare with the one Xcode installs. Installing still has to be the Xcode run above.

## On the iPhone, after you have installed that signed build

1. Tap Enroll. The Face ID prompt is the Secure Enclave access control (`biometryCurrentSet` and `privateKeyUsage`). Cancel once and confirm no pairing file is offered as a new active key.
2. Enroll, then Rotate, then Show request. Read the lines. Tap Sign and answer Face ID only after they match the package you mean.
3. Edit the package after Show request. Sign stays disabled until you show the request again.
4. Revoke. A later sign must not produce a signature.
5. Carry the pairing JSON to the Mac and pin it in Workflows. The status must say the Secure Enclave label was not accepted.

A signature is evidence the hardware key signed those bytes after a biometric check. It is not evidence you understood a command, and it does not start a run. A run still requires you to type `APPROVE` yourself, and only after you have chosen which executor guarantee is required.
