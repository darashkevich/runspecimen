# Human acceptance — unpublished 0.2.0rc15

This sheet is not packed into the sdist. It is not a production sign-off. It
does not authorize a merge, tag, notarization, install, or upload. An agent
must not type `APPROVE`, pass `--human-invoked` or `-allowProvisioningUpdates`,
or invoke biometrics.

Candidate pack: `artifacts/0.2.0rc15-2026-10-07-qafix/`. Engine identity:
`0.2.0rc15` (never published). Prior packs, including
`artifacts/0.2.0rc15-2026-10-06-bump/`, were not overwritten.

## Why every command is an absolute venv path

A prior human N10 run on the owner's Mac reported
`contract contains unknown field(s): execution_approval`. That was not an rc15
defect. Bare `runspecimen` on `PATH` was a Homebrew `0.2.0rc13` install, and
bare `python3` imported an rc11 copy. Neither knows `execution_approval`. The
rc15 wheel refuses with `execution policy local has no typed-phrase fallback`
before any prompt.

Do not use Homebrew, user site-packages, another checkout, or a shadowed
`~/.local/bin` shim for this sheet. `command -v runspecimen` may still print
one of those; that is why the provenance step records it and then aborts unless
`$VENV/bin/runspecimen` is rc15.

Every command below is one copy-pasteable line. Do not add trailing comments
on command lines.

## N1 — isolate a venv from this pack's wheel

```
export PACK="$PWD/artifacts/0.2.0rc15-2026-10-07-qafix"; export WHEEL="$PACK/runspecimen-0.2.0rc15-py3-none-any.whl"; export VENV="$PWD/.venv-rc15-human"; export RS="$VENV/bin/runspecimen"; export PY="$VENV/bin/python"; export WS="/tmp/rs-ha-rc15-$$"
```

```
test -f "$WHEEL"
```

```
python3 -m venv "$VENV"
```

The only bare `python3` on this sheet is the line above, which creates the
venv. After it, do not call `python3` or `runspecimen`.

## N2 — install the wheel by absolute path

```
"$PY" -m pip install --upgrade pip
```

```
"$PY" -m pip install --no-deps "$WHEEL"
```

## N3 — provenance (abort unless this is the rc15 wheel)

```
command -v runspecimen; "$RS" --version; "$PY" -c "import hashlib, os, pathlib, sys, runspecimen, runspecimen.contract as c; wheel=pathlib.Path(os.environ['WHEEL']).resolve(); sums=pathlib.Path(os.environ['PACK'])/'SHA256SUMS'; expected_wheel=next((line.split()[0] for line in sums.read_text().splitlines() if line.endswith('  '+wheel.name) or line.endswith(' '+wheel.name)), None); got_wheel=hashlib.sha256(wheel.read_bytes()).hexdigest(); contract=pathlib.Path(c.__file__).resolve(); got_contract=hashlib.sha256(contract.read_bytes()).hexdigest(); venv=pathlib.Path(os.environ['VENV']).resolve(); print('file', runspecimen.__file__); print('version', runspecimen.__version__); print('contract', contract); print('contract_sha256', got_contract); print('wheel_sha256', got_wheel); print('expected_wheel', expected_wheel); ok=(runspecimen.__version__=='0.2.0rc15' and str(pathlib.Path(runspecimen.__file__).resolve()).startswith(str(venv)) and got_contract=='d6c6c87f2d159ff5f64ffee0687034e829c5e5712b4738927fa237fdf84829e9' and expected_wheel==got_wheel); sys.exit(0 if ok else 1)"
```

Abort (non-zero) unless version is `0.2.0rc15`, the imported module lives under
`$VENV`, `contract.py` SHA-256 is
`d6c6c87f2d159ff5f64ffee0687034e829c5e5712b4738927fa237fdf84829e9`, and the
wheel SHA-256 matches `$PACK/SHA256SUMS`. Record the `command -v runspecimen`
path; it must not be the binary you invoke.

Expected `contract.py` SHA-256 is the rc15 module that knows
`execution_approval`. Do not change that expected N10 error in code.

## N4 — disposable workspace

```
"$RS" init-demo --workspace "$WS"
```

## N5 — doctor

```
"$RS" doctor --workspace "$WS"
```

## N6 — validate

```
"$RS" validate --workspace "$WS" --contract "$WS/contract.json"
```

## N7 — status

```
"$RS" status --workspace "$WS" --campaign-id demo-campaign --run-id run-001
```

## N8 — approve (human TTY only)

Run this yourself in a real terminal. Type `APPROVE` only if you intend to.
An agent must not type that phrase.

```
"$RS" approve --workspace "$WS" --contract "$WS/contract.json"
```

## N9 — preflight, run, postflight, verify

```
"$RS" preflight --workspace "$WS" --contract "$WS/contract.json"
```

```
"$RS" run --workspace "$WS" --contract "$WS/contract.json"
```

```
"$RS" postflight --workspace "$WS" --contract "$WS/contract.json"
```

```
"$RS" verify --workspace "$WS" --contract "$WS/contract.json" --campaign-id demo-campaign --run-id run-001
```

`verify` checks receipt integrity, the event chain, and live provenance. It
does not check HMAC or Ed25519 signatures.

## N10 — protected-policy refusal (not an unknown-field error)

This is the protected-policy negative. Expected: refuse before a prompt with
`execution policy local has no typed-phrase fallback`. Do not treat
`contract contains unknown field(s): execution_approval` as this result; that
string means an older install was invoked.

```
export WS10="/tmp/rs-ha-rc15-n10-$$"; "$RS" init-demo --workspace "$WS10"; "$PY" -c "import json, os, pathlib; p=pathlib.Path(os.environ['WS10'])/'contract.json'; doc=json.loads(p.read_text()); doc['execution_approval']='local'; p.write_text(json.dumps(doc, indent=2)+'\n')"
```

```
"$RS" approve --workspace "$WS10" --contract "$WS10/contract.json"
```

That approve must exit non-zero before any `APPROVE` prompt.

## Schema-rejection check (not N10)

This is a separate unknown-field check. Use a field that rc15 does not define.
Expected: `contract contains unknown field(s): not_a_real_contract_field`.

```
export WSUNK="/tmp/rs-ha-rc15-unk-$$"; "$RS" init-demo --workspace "$WSUNK"; "$PY" -c "import json, os, pathlib; p=pathlib.Path(os.environ['WSUNK'])/'contract.json'; doc=json.loads(p.read_text()); doc['not_a_real_contract_field']=True; p.write_text(json.dumps(doc, indent=2)+'\n')"
```

```
"$RS" validate --workspace "$WSUNK" --contract "$WSUNK/contract.json"
```

## Record

Return: `command -v runspecimen`, `$RS --version`, imported `__file__` /
`__version__` / `contract.py` SHA-256, wheel SHA-256, N8/N9 campaign and run
ids, `verify` exit status, N10 refusal text, and the schema-rejection text.
Do not install a holder. Do not close E2. `run_integration_complete` and
`e2_closed` stay false.
