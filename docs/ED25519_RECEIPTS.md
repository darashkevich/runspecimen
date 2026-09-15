# Ed25519 receipt signatures (optional)

Optional asymmetric signing for offline public-key verification of
`certificate.json` documents. Default Community installs stay **stdlib-only**.

Ed25519 is **not** an OS sandbox, compliance product, or transparency log.

## Install

```bash
python3 -m pip install 'runspecimen[ed25519]'
# alias:
python3 -m pip install 'runspecimen[signing]'
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

# Offline verify with an externally trusted public key (required for ok:true):
runspecimen verify-signature --workspace . --scheme ed25519 \
  --signed .runspecimen/runs/.../certificate.ed25519.json \
  --public-key ./team1.pub
# or --key-id team1 to use the workspace *.ed25519.pub trust file
```

HMAC remains available as `--scheme hmac` (default) and is still a shared-secret
MAC — not a digital signature.

## Trust language

- **Signature consistency**: the signature verifies under some public key (including
  one embedded in the signed document). Alone, this is **not** trusted success —
  an attacker can embed their own key and sign a forged receipt.
- **Trusted success** (`ok: true`): the signature verifies under an **externally
  trusted** public key (`--public-key` or workspace `--key-id` / `*.ed25519.pub`).
- Soft keys on disk are only as strong as filesystem custody and rotation.
- Key rotation (`keygen --overwrite`) stages new private/public files under
  exclusive no-follow temps, fsyncs, then renames so the live private key is
  never removed before the new public key is installed. A failed mid-rotation
  restores the previous working pair.
- Private and public key reads open with `O_NOFOLLOW` and validate the opened
  file descriptor (`fstat`) — not a separate path-based lstat-then-open race.
- This does **not** prove a scientific or engineering claim is true.
- Do not call HMAC a digital signature; do not promise absolute non-repudiation.
- Optional Ed25519 ≠ sandbox, job scheduler, or append-only transparency log.
