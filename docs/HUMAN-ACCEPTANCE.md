# Human acceptance — unpublished 0.2.0rc15

This sheet is not packed into the sdist. It is not a production sign-off. It
does not authorize a merge, tag, notarization, install, or upload. An agent
must not type `APPROVE`, pass `--human-invoked` or `-allowProvisioningUpdates`,
or invoke biometrics.

Candidate pack: `artifacts/0.2.0rc15-2026-10-08-qafix6/`. Engine identity:
`0.2.0rc15` (never published). Prior packs, including
`artifacts/0.2.0rc15-2026-10-08-qafix5/`,
`artifacts/0.2.0rc15-2026-10-08-qafix4/`,
`artifacts/0.2.0rc15-2026-10-07-qafix3/`,
`artifacts/0.2.0rc15-2026-10-07-qafix2/`,
`artifacts/0.2.0rc15-2026-10-07-qafix/` and
`artifacts/0.2.0rc15-2026-10-06-bump/`, were not overwritten.

You can paste this whole sheet into a fresh macOS Terminal (zsh, the default)
or into bash. You do not need extra wrappers, and you do not need to turn
shell options on or off.

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

A same-version tree can still be selected from inside that new venv.
`PYTHONPATH`, a `.pth` path-prepend, sitecustomize, or an executable `.pth`
import can load old approval code while the top-level package still looks
right. The provenance step therefore binds every loaded `runspecimen.*`
module (including `runspecimen.approve`) to the hashed installed files, using
the absolute launcher's own interpreter. That interpreter must be named by an
absolute shebang; `#!/usr/bin/env python3` is refused. The check assumes a
trusted interpreter — it does not claim to resist someone replacing Python
itself.

Do not use Homebrew, user site-packages, another checkout, or a shadowed
`~/.local/bin` shim for this sheet. `command -v runspecimen` may still print
one of those; that is informational and does not gate the session.

Stop if any step prints `FAIL`. Do not continue. Earlier sessions' notes stay
as they are; do not go back and invent exit codes that were not printed then.

## N1 — brand-new venv (abort if the target already exists)

Paste this first. It remembers the pack path and defines four tiny helpers.
`rs` and `py` always use the venv copies, with a clean Python environment.
`rs_ok` is for steps that must succeed. `rs_neg` is for the two expected
refusals later.

```
export PACK="$PWD/artifacts/0.2.0rc15-2026-10-08-qafix6"
export WHEEL="$PACK/runspecimen-0.2.0rc15-py3-none-any.whl"
export WORK=$(mktemp -d "${TMPDIR:-/tmp}/rs-ha-rc15.XXXXXX")
export VENV="$WORK/venv"
export RS="$VENV/bin/runspecimen"
export PY="$VENV/bin/python"
export WS="$WORK/ws-demo"
rs() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 "$RS" "$@"; }
py() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 "$PY" "$@"; }
rs_ok() { echo "STEP $1 exit=$2"; if [ "$2" -ne 0 ]; then echo "FAIL: step $1 expected exit 0, got $2. Stop here; do not continue."; exit 1; fi; }
rs_neg() { echo "STEP $1 exit=$2"; echo "$3"; if [ "$2" -eq 0 ]; then echo "FAIL: step $1 expected a refusal (nonzero exit), got 0. Stop here."; exit 1; fi; if printf '%s\n' "$3" | grep -Fqx -- "$4"; then echo "PASS: $1"; else echo "FAIL: step $1 did not print the expected message as a complete line:"; echo "  $4"; exit 1; fi; }
```

```
test -f "$WHEEL"
rs_ok N1-wheel $?
```

```
test ! -e "$VENV"
rs_ok N1-venv-absent $?
```

```
python3 -m venv "$VENV"
rs_ok N1-venv $?
```

The only bare `python3` on this sheet is the line above, which creates the
venv. After it, do not call `python3` or `runspecimen`. `test ! -e "$VENV"`
must run before `venv`; a leftover directory is an abort, not an upgrade.

## N2 — hash the pinned wheel, then install only that file

```
py -c "import hashlib, os, pathlib, sys; wheel=pathlib.Path(os.environ['WHEEL']).resolve(); sums=pathlib.Path(os.environ['PACK'])/'SHA256SUMS'; expected=next((line.split()[0] for line in sums.read_text().splitlines() if line.endswith('  '+wheel.name)), None); got=hashlib.sha256(wheel.read_bytes()).hexdigest(); print('wheel_sha256', got); print('expected_wheel', expected); sys.exit(0 if expected==got else 1)"
rs_ok N2-hash $?
```

```
py -m pip install --no-index --no-deps --force-reinstall "$WHEEL"
rs_ok N2-install $?
```

Do not upgrade pip in this venv. Do not install from PyPI or another path.

## N3 — provenance (installed bytes vs the pinned wheel zip)

```
command -v runspecimen
```

```
rs --version
rs_ok N3-version $?
py "$PWD/scripts/verify_installed_wheel.py" --wheel "$WHEEL" --launcher "$RS"
rs_ok N3-verify $?
```

`command -v runspecimen` is informational. If the launcher is missing, N3-version
prints `FAIL` and stops; do not continue to N4.

Abort unless every hashed RECORD member in the wheel, and every
`runspecimen/*.py` in that zip, matches the file installed under the absolute
launcher's own interpreter, every loaded `runspecimen.*` origin (including
`runspecimen.approve`, `runspecimen.present`, and the CLI) is realpath-equal to the hashed installed
member, the sanitized environment has no import overrides, sitecustomize is
absent, and no site-packages `.pth` adds a path outside that install or an
executable import that is not a known-safe exact body. The script prints the
installed dist-info `RECORD` and `direct_url.json`. `__version__ ==
0.2.0rc15` is not sufficient: the 2026-10-06-bump wheel reports the same
version and must fail this step when `$WHEEL` is the qafix6 pin. A
same-version tree selected via inside-venv `PYTHONPATH`, a `.pth` prepend,
sitecustomize, or an executable `.pth` import must also fail.

Record the `command -v runspecimen` path; it must not be the binary you invoke.

## N4 — disposable workspace

```
rs init-demo --workspace "$WS"
rs_ok N4 $?
```

## N5 — doctor

Use default JSON on this sheet (`rs doctor …`). `--pretty` is optional human
view and must not be used for acceptance; JSON contracts and exit codes stay
the default.

```
rs doctor --workspace "$WS"
rs_ok N5 $?
```

## N6 — validate

```
rs validate --workspace "$WS" --contract "$WS/contract.json"
rs_ok N6 $?
```

## N7 — status

```
rs status --workspace "$WS" --campaign-id demo-campaign --run-id run-001
rs_ok N7 $?
```

## N8 — approve (human TTY only)

Run this yourself in a real terminal. Type `APPROVE` only if you intend to.
An agent must not type that phrase. Use the same `rs` helper as N3–N7.

```
rs approve --workspace "$WS" --contract "$WS/contract.json"
rs_ok N8 $?
```

Write down the `STEP N8 exit=` line. `rs_ok` asserts exit 0 and stops before
N9 on failure, same as the other positive steps. Only you may type the phrase.

## N9 — preflight, run, postflight, verify

Sequential. Use the same `rs` helper. The campaign and run identities must
stay `demo-campaign` / `run-001`.

```
rs preflight --workspace "$WS" --contract "$WS/contract.json"
rs_ok N9-preflight $?
```

```
rs run --workspace "$WS" --contract "$WS/contract.json"
rs_ok N9-run $?
```

```
rs postflight --workspace "$WS" --contract "$WS/contract.json"
rs_ok N9-postflight $?
```

```
rs verify --workspace "$WS" --contract "$WS/contract.json" --campaign-id demo-campaign --run-id run-001
rs_ok N9-verify $?
```

`verify` checks receipt integrity, the event chain, and live provenance. It
does not check HMAC or Ed25519 signatures.

## N10 — protected-policy refusal (not an unknown-field error)

This is the protected-policy negative. Expected: refuse before a prompt with
`execution policy local has no typed-phrase fallback`. Do not treat
`contract contains unknown field(s): execution_approval` as this result; that
string means an older install was invoked. No prompt.

```
export WS10="/tmp/rs-ha-rc15-n10-$$"
rs init-demo --workspace "$WS10"
rs_ok N10-init $?
py -c "import json, os, pathlib; p=pathlib.Path(os.environ['WS10'])/'contract.json'; doc=json.loads(p.read_text()); doc['execution_approval']='local'; p.write_text(json.dumps(doc, indent=2)+'\n')"
rs_ok N10-edit $?
```

```
_rs_n=0
_rs_out=$(rs approve --workspace "$WS10" --contract "$WS10/contract.json" 2>&1) || _rs_n=$?
rs_neg N10 "$_rs_n" "$_rs_out" "RunSpecimen error: execution policy local has no typed-phrase fallback"
```

That approve must exit non-zero before any `APPROVE` prompt.

## Schema-rejection check (not N10)

This is a separate unknown-field check. Use a field that rc15 does not define.
Expected: `contract contains unknown field(s): not_a_real_contract_field`.

```
export WSUNK="/tmp/rs-ha-rc15-unk-$$"
rs init-demo --workspace "$WSUNK"
rs_ok UNK-init $?
py -c "import json, os, pathlib; p=pathlib.Path(os.environ['WSUNK'])/'contract.json'; doc=json.loads(p.read_text()); doc['not_a_real_contract_field']=True; p.write_text(json.dumps(doc, indent=2)+'\n')"
rs_ok UNK-edit $?
```

```
_rs_n=0
_rs_out=$(rs validate --workspace "$WSUNK" --contract "$WSUNK/contract.json" 2>&1) || _rs_n=$?
rs_neg UNK "$_rs_n" "$_rs_out" "RunSpecimen error: contract contains unknown field(s): not_a_real_contract_field"
```

## Record

Every setup and provenance step prints `STEP <id> exit=<n>` and checks it
immediately. `command -v` is informational and does not gate. Keep the
printed `STEP` lines in your notes. Do not reconstruct earlier exit codes
from a previous session that did not print them.

N3 must show: the absolute launcher (`$RS`) run, its interpreter and prefix,
every loaded `runspecimen.*` origin bound to the hashed installed member
(realpath-equal, including `runspecimen.approve` and the CLI), the
installed-file comparison, installed `RECORD` and `direct_url.json`,
`STEP N3-version exit=0`, `STEP N3-verify exit=0`, and no import overrides
(`PYTHONPATH` / `PYTHONHOME` / `PYTHONSTARTUP` unset, `PYTHONNOUSERSITE=1`,
no outside-install `.pth`, no sitecustomize).

N4–N7 use the same `rs` helper.

N8 is a real human approval in a real terminal. An agent must not type `APPROVE`.

N9 is sequential `preflight`, `run`, `postflight`, `verify` with matching
`demo-campaign` / `run-001` identities.

N10 is unchanged: exact `execution policy local has no typed-phrase fallback`
refusal, no prompt. Do not treat an unknown-field error as N10. The sheet
prints `PASS: N10` only when the exit is nonzero and that exact refusal is
present as a complete line
(`RunSpecimen error: execution policy local has no typed-phrase fallback`).

The schema-rejection check is separate and uses `not_a_real_contract_field`.
It prints `PASS: UNK` only when the exit is nonzero and that exact unknown-field
refusal is present as a complete line
(`RunSpecimen error: contract contains unknown field(s): not_a_real_contract_field`).

Do not install a holder. Do not close E2. `run_integration_complete` and
`e2_closed` stay false.

## Labeled supplement transcript

The original human transcript from the earlier session stays as-is. Do not
edit it. Do not fill in missing `STEP` lines for that older run.

If you already completed N8–N9 under that earlier run ID, do not replay the
positive run. Capture a new labeled supplement instead, in a fresh Terminal,
with a new workspace:

```
Session: HUMAN-ACCEPTANCE supplement qafix6
Date:
Pack: artifacts/0.2.0rc15-2026-10-08-qafix6/
Paste N1 through N7, then N10 and the schema-rejection check.
Copy every "STEP … exit=" line, plus PASS: N10 and PASS: UNK, into your notes.
```

A new N8 is a new approval. An agent must not type `APPROVE`.
