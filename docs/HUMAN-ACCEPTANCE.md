# Human acceptance — unpublished 0.2.0rc15

This sheet is not packed into the sdist. It is not a production sign-off. It
does not authorize a merge, tag, notarization, install, or upload. An agent
must not type `APPROVE`, pass `--human-invoked` or `-allowProvisioningUpdates`,
or invoke biometrics.

Candidate pack: `artifacts/0.2.0rc15-2026-10-08-qafix4/`. Engine identity:
`0.2.0rc15` (never published). Prior packs, including
`artifacts/0.2.0rc15-2026-10-07-qafix3/`,
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

A same-version tree can still be selected from inside that new venv. Installing
the pinned wheel and then importing via `PYTHONPATH` or a `.pth` path-prepend
under `$VENV/older` runs the old bytes while a prefix-ancestor check would
pass. The provenance step therefore binds `runspecimen.__file__` and the CLI
entry module to the exact verified package directory (realpath equality, not a
venv ancestor), using the absolute launcher's interpreter and the same
sanitized environment as every later `$RS` call.

Do not use Homebrew, user site-packages, another checkout, or a shadowed
`~/.local/bin` shim for this sheet. `command -v runspecimen` may still print
one of those; that is informational and does not gate the session.

Every command below is one copy-pasteable line. Do not add trailing comments
on command lines. Stop the session if any mandatory setup or provenance
command exits non-zero (`|| exit` or `set -euo pipefail`). `command -v` is
not mandatory.

## N1 — brand-new venv (abort if the target already exists)

```
export PACK="$PWD/artifacts/0.2.0rc15-2026-10-08-qafix4"; export WHEEL="$PACK/runspecimen-0.2.0rc15-py3-none-any.whl"; export WORK=$(mktemp -d "${TMPDIR:-/tmp}/rs-ha-rc15.XXXXXX"); export VENV="$WORK/venv"; export RS="$VENV/bin/runspecimen"; export PY="$VENV/bin/python"; export WS="$WORK/ws-demo"; export RS_SANITIZE='env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1'
```

```
test -f "$WHEEL" || exit
```

```
test ! -e "$VENV" || exit
```

```
python3 -m venv "$VENV" || exit
```

The only bare `python3` on this sheet is the line above, which creates the
venv. After it, do not call `python3` or `runspecimen`. `test ! -e "$VENV"`
must run before `venv`; a leftover directory is an abort, not an upgrade.
`$RS_SANITIZE` is the only environment used for verification and for every
later `$RS` / `$PY` call.

## N2 — hash the pinned wheel, then install only that file

```
$RS_SANITIZE "$PY" -c "import hashlib, os, pathlib, sys; wheel=pathlib.Path(os.environ['WHEEL']).resolve(); sums=pathlib.Path(os.environ['PACK'])/'SHA256SUMS'; expected=next((line.split()[0] for line in sums.read_text().splitlines() if line.endswith('  '+wheel.name)), None); got=hashlib.sha256(wheel.read_bytes()).hexdigest(); print('wheel_sha256', got); print('expected_wheel', expected); sys.exit(0 if expected==got else 1)" || exit
```

```
$RS_SANITIZE "$PY" -m pip install --no-index --no-deps --force-reinstall "$WHEEL" || exit
```

Do not upgrade pip in this venv. Do not install from PyPI or another path.

## N3 — provenance (installed bytes vs the pinned wheel zip)

```
command -v runspecimen
```

```
set -euo pipefail; $RS_SANITIZE "$RS" --version && $RS_SANITIZE "$PY" "$PWD/scripts/verify_installed_wheel.py" --wheel "$WHEEL" --launcher "$RS"
```

`command -v runspecimen` is informational. Successful `$RS --version` is a
prerequisite (`&&`) of the verifier. A missing or failing launcher stops the
session; do not continue to N4.

Abort (non-zero) unless every hashed RECORD member in the wheel, and every
`runspecimen/*.py` in that zip, matches the file installed under the absolute
launcher's interpreter, the effective `runspecimen.__file__` and CLI module
(`runspecimen.cli.__file__` / console-script target) realpath-equal that
verified package directory, the sanitized environment has no import overrides,
and no site-packages `.pth` adds a path outside that install. The script prints
the installed dist-info `RECORD` and `direct_url.json`. `__version__ ==
0.2.0rc15` is not sufficient: the 2026-10-06-bump wheel reports the same
version and must fail this step when `$WHEEL` is the qafix4 pin. A
same-version tree selected via inside-venv `PYTHONPATH` or a `.pth` prepend
must also fail.

Record the `command -v runspecimen` path; it must not be the binary you invoke.

## N4 — disposable workspace

```
$RS_SANITIZE "$RS" init-demo --workspace "$WS" || exit
```

## N5 — doctor

```
$RS_SANITIZE "$RS" doctor --workspace "$WS" || exit
```

## N6 — validate

```
$RS_SANITIZE "$RS" validate --workspace "$WS" --contract "$WS/contract.json" || exit
```

## N7 — status

```
$RS_SANITIZE "$RS" status --workspace "$WS" --campaign-id demo-campaign --run-id run-001 || exit
```

## N8 — approve (human TTY only)

Run this yourself in a real terminal. Type `APPROVE` only if you intend to.
An agent must not type that phrase. Use the same absolute launcher and
sanitized environment as N3–N7.

```
$RS_SANITIZE "$RS" approve --workspace "$WS" --contract "$WS/contract.json"
```

## N9 — preflight, run, postflight, verify

Sequential. Use the same absolute launcher and sanitized environment. The
campaign and run identities must stay `demo-campaign` / `run-001`.

```
$RS_SANITIZE "$RS" preflight --workspace "$WS" --contract "$WS/contract.json" || exit
```

```
$RS_SANITIZE "$RS" run --workspace "$WS" --contract "$WS/contract.json" || exit
```

```
$RS_SANITIZE "$RS" postflight --workspace "$WS" --contract "$WS/contract.json" || exit
```

```
$RS_SANITIZE "$RS" verify --workspace "$WS" --contract "$WS/contract.json" --campaign-id demo-campaign --run-id run-001 || exit
```

`verify` checks receipt integrity, the event chain, and live provenance. It
does not check HMAC or Ed25519 signatures.

## N10 — protected-policy refusal (not an unknown-field error)

This is the protected-policy negative. Expected: refuse before a prompt with
`execution policy local has no typed-phrase fallback`. Do not treat
`contract contains unknown field(s): execution_approval` as this result; that
string means an older install was invoked. No prompt.

```
export WS10="/tmp/rs-ha-rc15-n10-$$"; $RS_SANITIZE "$RS" init-demo --workspace "$WS10" || exit; $RS_SANITIZE "$PY" -c "import json, os, pathlib; p=pathlib.Path(os.environ['WS10'])/'contract.json'; doc=json.loads(p.read_text()); doc['execution_approval']='local'; p.write_text(json.dumps(doc, indent=2)+'\n')" || exit
```

```
$RS_SANITIZE "$RS" approve --workspace "$WS10" --contract "$WS10/contract.json"
```

That approve must exit non-zero before any `APPROVE` prompt.

## Schema-rejection check (not N10)

This is a separate unknown-field check. Use a field that rc15 does not define.
Expected: `contract contains unknown field(s): not_a_real_contract_field`.

```
export WSUNK="/tmp/rs-ha-rc15-unk-$$"; $RS_SANITIZE "$RS" init-demo --workspace "$WSUNK" || exit; $RS_SANITIZE "$PY" -c "import json, os, pathlib; p=pathlib.Path(os.environ['WSUNK'])/'contract.json'; doc=json.loads(p.read_text()); doc['not_a_real_contract_field']=True; p.write_text(json.dumps(doc, indent=2)+'\n')" || exit
```

```
$RS_SANITIZE "$RS" validate --workspace "$WSUNK" --contract "$WSUNK/contract.json"
```

## Record

Every setup and provenance step's exit status is recorded and gates the
session. `command -v` is informational and does not gate.

N3 must show: the absolute launcher (`$RS`) run, its interpreter and prefix,
effective `runspecimen.__file__` and CLI module origins bound to the compared
install (realpath-equal to the verified package directory), the installed-file
comparison, installed `RECORD` and `direct_url.json`, exit 0, and no import
overrides (`PYTHONPATH` / `PYTHONHOME` / `PYTHONSTARTUP` unset,
`PYTHONNOUSERSITE=1`, no outside-install `.pth`).

N4–N7 use the same absolute launcher and sanitized environment.

N8 is a real human approval in a real terminal. An agent must not type `APPROVE`.

N9 is sequential `preflight`, `run`, `postflight`, `verify` with matching
`demo-campaign` / `run-001` identities.

N10 is unchanged: exact `execution policy local has no typed-phrase fallback`
refusal, no prompt. Do not treat an unknown-field error as N10.

The schema-rejection check is separate and uses `not_a_real_contract_field`.

Do not install a holder. Do not close E2. `run_integration_complete` and
`e2_closed` stay false.
