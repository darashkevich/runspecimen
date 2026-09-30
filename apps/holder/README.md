# RunSpecimen Holder (Developer ID)

Separate product from the Mac App Store app. Bundle id
`com.darashkevich.runspecimen.holder`. Install path
`/Applications/RunSpecimen Holder.app`.

## Mechanism

Embedded `SMAppService.daemon` (`com.darashkevich.runspecimen.holder.daemon`).
Not a per-user LaunchAgent. Not a hand-copied `/Library/LaunchDaemons` plist.

The daemon runs as root, owns
`/Library/Application Support/com.darashkevich.runspecimen.holder/state`
(mode `0700`), and serves the authenticated AF_UNIX holder protocol with
`allow_test_double` off and `installed_protection` on. A same-user process must
not rewrite enrollment, policy, consumed nonces, or leases. Administrator or
root can still defeat this holder. This is not human-only execution and not
Store parity.

## Entitlements

`Entitlements/RunSpecimenHolder.entitlements` is an empty dict. Apple’s
`SMAppService` API requires a code-signed app; it does not require additional
entitlement keys for daemon registration. `network.server` and `get-task-allow`
are intentionally absent.

## Build / install

```sh
apps/holder/Scripts/build_install_holder.sh
```

Signs with `Developer ID Application: YAHOR DARASHKEVICH (UN6KF8636A)`.
Does not touch `/Applications/RunSpecimen.app`. Does not notarize.

After install, macOS may show **System Settings → General → Login Items &
Extensions** and ask you to allow Background Items for RunSpecimen Holder.
An admin password may be required. An agent must not click that dialog.
