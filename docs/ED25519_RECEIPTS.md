# Ed25519 receipt signatures (optional)

Optional asymmetric signing for offline public-key verification of
`certificate.json` documents. Default Community installs stay **stdlib-only**.

## Install

```bash
python3 -m pip install 'runspecimen[ed25519]'
# or from a checkout:
python3 -m pip install '.[ed25519]'
```

## Commands

```bash
runspecimen keygen --workspace . --scheme ed25519 --key-id team1
runspecimen export-public-key --workspace . --key-id team1 --output ./team1.pub

# After a verified postflight certificate exists:
runspecimen sign --workspace . --scheme ed25519 --key-id team1 \
  --certificate .runspecimen/runs/.../certificate.json \
  --contract contract.json

# Offline verify with public key only (no private key, no --contract):
runspecimen verify-signature --workspace . --scheme ed25519 \
  --signed .runspecimen/runs/.../certificate.ed25519.json \
  --public-key ./team1.pub
```

HMAC remains available as `--scheme hmac` (default) and is still a shared-secret
MAC — not a digital signature.

## Trust language

- Ed25519 proves the certificate bytes were signed by a holder of the matching
  private key for the stated public key.
- Soft keys on disk are only as strong as filesystem custody and rotation.
- This does **not** prove a scientific or engineering claim is true.
- Do not call HMAC a digital signature; do not promise absolute non-repudiation.
