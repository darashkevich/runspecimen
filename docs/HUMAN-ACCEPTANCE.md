# Human acceptance — unpublished 0.2.0rc15

This sheet is not packed into the sdist. It is not a production sign-off. It
does not authorize a merge, tag, notarization, install, or upload. An agent
must not type `APPROVE`, pass `--human-invoked` or `-allowProvisioningUpdates`,
or invoke biometrics.

Candidate pack: `artifacts/0.2.0rc15-2026-10-07-qafix3/`. Engine identity:
`0.2.0rc15` (never published). Prior packs, including
`artifacts/0.2.0rc15-2026-10-07-qafix2/`,
`artifacts/0.2.0rc15-2026-10-07-qafix/` and
`artifacts/0.2.0rc15-2026-10-06-bump/`, were not overwritten.

## Why every command is an absolute venv path

A prior human N10 run on the owner's Mac reported
`contract contains unknown field(s): execution_approval`. That was not an rc15
defect. Bare `runspecimen` on `PATH` was a Homebrew `0.2.0rc13` install, and
bare `python3` imported an rc11 copy. Neither knows `execution_approval`. The
rc15 wheel refuses with `execution policy local has no typed-phrase fallback`
before any prompt.

A later reuse of an existing venv left the 2026-10-06-bump rc15 install in
place while a version-only provenance check passed: both wheels report
`0.2.0rc15`, and hashing the new wheel file on disk does not prove that tree
is what is imported. Version strings are not proof. Do not reuse a venv. Do
not pip-upgrade an existing venv. Create a brand-new directory every run.

Do not use Homebrew, user site-packages, another checkout, or a shadowed
`~/.local/bin` shim for this sheet. `command -v runspecimen` may still print
one of those; that is why the provenance step records it and then compares
installed bytes to the pinned wheel zip.

Every command below is one copy-pasteable line. Do not add trailing comments
on command lines.

## N1 — brand-new venv (abort if the target already exists)

```
export PACK="$PWD/artifacts/0.2.0rc15-2026-10-07-qafix3"; export WHEEL="$PACK/runspecimen-0.2.0rc15-py3-none-any.whl"; export WORK=$(mktemp -d "${TMPDIR:-/tmp}/rs-ha-rc15.XXXXXX"); export VENV="$WORK/venv"; export RS="$VENV/bin/runspecimen"; export PY="$VENV/bin/python"; export WS="$WORK/ws-demo"
```

```
test -f "$WHEEL"
```

```
test ! -e "$VENV"
```

```
python3 -m venv "$VENV"
```

The only bare `python3` on this sheet is the line above, which creates the
venv. After it, do not call `python3` or `runspecimen`. `test ! -e "$VENV"`
must run before `venv`; a leftover directory is an abort, not an upgrade.

## N2 — hash the pinned wheel, then install only that file

```
"$PY" -c "import hashlib, os, pathlib, sys; wheel=pathlib.Path(os.environ['WHEEL']).resolve(); sums=pathlib.Path(os.environ['PACK'])/'SHA256SUMS'; expected=next((line.split()[0] for line in sums.read_text().splitlines() if line.endswith('  '+wheel.name)), None); got=hashlib.sha256(wheel.read_bytes()).hexdigest(); print('wheel_sha256', got); print('expected_wheel', expected); sys.exit(0 if expected==got else 1)"
```

```
"$PY" -m pip install --no-index --no-deps --force-reinstall "$WHEEL"
```

Do not upgrade pip in this venv. Do not install from PyPI or another path.

## N3 — provenance (installed bytes vs the pinned wheel zip)

```
command -v runspecimen; "$RS" --version; "$PY" "$PWD/scripts/verify_installed_wheel.py" --wheel "$WHEEL"
```

Abort (non-zero) unless every hashed RECORD member in the wheel, and every
`runspecimen/*.py` in that zip, matches the file installed under `$PY`, with
no extra installed `.py` modules. The script prints the installed dist-info
`RECORD` and `direct_url.json`. `__version__ == 0.2.0rc15` is not sufficient:
the 2026-10-06-bump wheel reports the same version and must fail this step
when `$WHEEL` is the qafix3 pin.

Record the `command -v runspecimen` path; it must not be the binary you invoke.

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

Return: `command -v runspecimen`, `$RS --version`, the provenance script JSON
(including installed `RECORD` and `direct_url.json`), N8/N9 campaign and run
ids, `verify` exit status, N10 refusal text, and the schema-rejection text.
Do not install a holder. Do not close E2. `run_integration_complete` and
`e2_closed` stay false.
