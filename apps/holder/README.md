# RunSpecimen Holder (Developer ID)

Separate product from the Mac App Store app. Bundle id
`com.darashkevich.runspecimen.holder`. The Store app is guarantee (1), a typed
`APPROVE` phrase. This holder is guarantee (2) and is not part of that app.
Nothing in this candidate installs or notarizes Holder.app. Production device
verification fails closed unless a vetted verifier is connected. A software
signature is not Touch ID, Face ID, or a Secure Enclave.

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
RS_HOLDER_STAGE_FIXTURES=1 RS_HOLDER_RUNTIME_SOURCE=/path/to/python3 \
  apps/holder/Scripts/build_install_holder.sh stage
```

`stage` creates a unique directory and an embedded `Resources/Runtime/bin/python3`.
It does not delete `HOLDER_BUILD_DIR` and it does not install. `install`,
`update`, `rollback`, and `uninstall` exit 4. They are not run from this pass.
`/usr/bin/python3` is not a fallback. Does not touch `/Applications/RunSpecimen.app`.
Does not notarize.

After install, macOS may show **System Settings → General → Login Items &
Extensions** and ask you to allow Background Items for RunSpecimen Holder.
An admin password may be required. An agent must not click that dialog.
