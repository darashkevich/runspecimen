# Human acceptance — unpublished 0.2.0rc15

This sheet is not packed into the sdist. It is not a production sign-off. It
does not authorize a merge, tag, notarization, install, or upload. An agent
must not type `APPROVE`, pass `--human-invoked` or `-allowProvisioningUpdates`,
or invoke biometrics.

Candidate pack: `artifacts/0.2.0rc15-2026-10-09-qafix13/`. Engine identity:
`0.2.0rc15` (never published). Prior packs, including
`artifacts/0.2.0rc15-2026-10-09-qafix12/` (CC-04-only snapshot; not this sheet),
`artifacts/0.2.0rc15-2026-10-09-qafix11/` (in-place edits; not this sheet),
`artifacts/0.2.0rc15-2026-10-08-qafix10/`,
`artifacts/0.2.0rc15-2026-10-08-qafix9/`,
`artifacts/0.2.0rc15-2026-10-08-qafix8/`,
`artifacts/0.2.0rc15-2026-10-08-qafix7/`,
`artifacts/0.2.0rc15-2026-10-08-qafix6/`,
`artifacts/0.2.0rc15-2026-10-08-qafix5/`,
`artifacts/0.2.0rc15-2026-10-08-qafix4/`,
`artifacts/0.2.0rc15-2026-10-07-qafix3/`,
`artifacts/0.2.0rc15-2026-10-07-qafix2/`,
`artifacts/0.2.0rc15-2026-10-07-qafix/` and
`artifacts/0.2.0rc15-2026-10-06-bump/`, were not overwritten.

Record these identities at the top of your notes before N1 (fill in from this
machine; N2 prints the full wheel digest):

- Candidate SHA: `git rev-parse HEAD` of this checkout
- Pack: `artifacts/0.2.0rc15-2026-10-09-qafix13/`
- Shell: `$SHELL` and `echo $ZSH_VERSION` or `echo $BASH_VERSION`
- python3: `command -v python3` and `python3 --version`
- Wheel SHA-256: `fb1a1fca5c1cbc10c9c448d3803f2d9fc9ba000778bd4e30762d06fed56aaac3` (must match N2 `wheel_sha256` and pack SHA256SUMS; `src/` is unchanged from `10e2f2f`)

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
absolute shebang; `#!/usr/bin/env python3` is refused. The launcher body after
the shebang must byte-match the pinned pip console-script template. The
verifier also refuses unexpected files in `$VENV/bin` (a `json.py` there would
shadow stdlib because the real launcher puts `bin/` on `sys.path[0]`). CPython
3.14 `python -m venv` also creates the exact `𝜋thon` symlink (U+1D70B); that
name is allowlisted. The verifier probes module origins by running `$RS doctor`,
not `python -c`.
`python -m runspecimen` from an untrusted cwd is not a supported verified
path; this sheet only invokes the absolute launcher. The
trusted interpreter assumption: the check trusts **only the Python interpreter and its stdlib**. It does not claim to resist someone replacing Python itself.
Venv-local metadata (setuptools RECORD, `_distutils_hack`) is not trust:
RECORD does not hash itself and is writable by the same attacker. Bytecode is
not trust: any `__pycache__` / `.pyc` under the installed package is refused.

Do not use Homebrew, user site-packages, another checkout, or a shadowed
`~/.local/bin` shim for this sheet. `command -v runspecimen` may still print
one of those; that is informational and does not gate the session.

Stop if any step prints `FAIL`. Do not continue. Earlier sessions' notes stay
as they are; do not go back and invent exit codes that were not printed then.

## N1 — brand-new venv (abort if the target already exists)

Paste this first. It remembers the pack path and defines four tiny helpers.
`rs` and `py` always use the venv copies, with a clean Python environment.
`rs_ok` is for steps that must succeed. `rs_neg` is for the two expected
refusals later. `CAMPAIGN_ID` / `RUN_ID` are set once and used for N4–N9.
Do not reuse an earlier session's run ID.

```
export PACK="$PWD/artifacts/0.2.0rc15-2026-10-09-qafix13"
export WHEEL="$PACK/runspecimen-0.2.0rc15-py3-none-any.whl"
export WORK=$(mktemp -d "${TMPDIR:-/tmp}/rs-ha-rc15.XXXXXX")
export VENV="$WORK/venv"
export RS="$VENV/bin/runspecimen"
export PY="$VENV/bin/python"
export WS="$WORK/ws-demo"
export CAMPAIGN_ID="ha-campaign"
export RUN_ID="ha-$(date +%Y%m%d-%H%M%S)-$$"
rs() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 "$RS" "$@"; }
py() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 "$PY" "$@"; }
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

```
"$PY" -m pip uninstall -y setuptools
rs_ok N1-setuptools $?
```

The only bare `python3` on this sheet is the `venv` line above, which creates
the venv. After it, do not call `python3` or `runspecimen`. `test ! -e "$VENV"`
must run before `venv`; a leftover directory is an abort, not an upgrade.
Uninstall setuptools before the wheel so `distutils-precedence.pth` and the
`_distutils_hack` shim are gone. Python 3.12+ venvs do not ship setuptools;
the uninstall is then a no-op and still prints `STEP N1-setuptools exit=0`.

## N2 — hash the pinned wheel, then install only that file

```
py -c "import hashlib, os, pathlib, sys; wheel=pathlib.Path(os.environ['WHEEL']).resolve(); sums=pathlib.Path(os.environ['PACK'])/'SHA256SUMS'; expected=next((line.split()[0] for line in sums.read_text().splitlines() if line.endswith('  '+wheel.name)), None); got=hashlib.sha256(wheel.read_bytes()).hexdigest(); print('wheel_sha256', got); print('expected_wheel', expected); sys.exit(0 if expected==got else 1)"
rs_ok N2-hash $?
```

```
py -m pip install --no-index --no-deps --force-reinstall --no-compile "$WHEEL"
rs_ok N2-install $?
```

Do not upgrade pip in this venv. Do not install from PyPI or another path.
`--no-compile` and `PYTHONDONTWRITEBYTECODE=1` keep bytecode off the hashed
sources. The verifier refuses any `__pycache__` / `.pyc` under the installed
package.

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
member, the sanitized environment has no import overrides, and the target
venv has no extra startup code. The launcher body after the shebang must
byte-match the pinned pip console-script template (shebang checked
separately). The verifier's probe runs with `-I -B` and refuses any
`.pyc` / `__pycache__` under the installed package, `PYTHONPYCACHEPREFIX` /
`sys.pycache_prefix`, and sourceless bytecode. The verifier trusts **only the Python interpreter and its stdlib**. In that venv it refuses: any `.pth` with
an executable `import` line (any name or owner, including leftover setuptools
`distutils-precedence.pth` / DistutilsMetaFinder), any importable
sitecustomize or usercustomize that is not the interpreter's own stdlib, any
non-stdlib `sys.meta_path` or `sys.path_hooks` entry after startup, and any
`_virtualenv*`. This sheet uses stdlib `python3 -m venv`, which creates none.
A stdlib finder is identified by its class living in a stdlib module whose
realpath is under the interpreter's stdlib dir, not by name.
There is no RECORD-based trust of `_distutils_hack`. The script prints the
installed dist-info `RECORD` and `direct_url.json`. `__version__ ==
0.2.0rc15` is not sufficient: the 2026-10-06-bump wheel reports the same
version and must fail this step when `$WHEEL` is the qafix13 pin. A
same-version tree selected via inside-venv `PYTHONPATH`, a `.pth` prepend,
sitecustomize, or an executable `.pth` import must also fail.

Record the `command -v runspecimen` path; it must not be the binary you invoke.

## N4 — disposable workspace

```
rs init-demo --workspace "$WS"
rs_ok N4 $?
```

```
py -c "import json, os, pathlib; p=pathlib.Path(os.environ['WS'])/'contract.json'; doc=json.loads(p.read_text()); doc['campaign_id']=os.environ['CAMPAIGN_ID']; doc['run_id']=os.environ['RUN_ID']; p.write_text(json.dumps(doc, indent=2)+'\n')"
rs_ok N4-ids $?
```

init-demo writes demo identities. N4-ids replaces them with the `CAMPAIGN_ID`
and `RUN_ID` exported in N1. Use those same values for N7–N9.

## N5 — doctor

Use default JSON on this sheet (`rs doctor …`). `--pretty` is optional human
view and must not be used for acceptance; JSON contracts and exit codes stay
the default. Doctor JSON may include `loaded_module_origins` (realpath of
every loaded module) so N3 can bind the real launcher process. Other default
JSON shapes are unchanged.

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
rs status --workspace "$WS" --campaign-id "$CAMPAIGN_ID" --run-id "$RUN_ID"
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
stay the `CAMPAIGN_ID` / `RUN_ID` exported in N1.

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
_rs_n=0
_rs_out=$(rs verify --workspace "$WS" --contract "$WS/contract.json" --campaign-id "$CAMPAIGN_ID" --run-id "$RUN_ID" 2>&1) || _rs_n=$?
printf '%s\n' "$_rs_out"
rs_ok N9-verify "$_rs_n"
printf '%s\n' "$_rs_out" > "$WORK/verify.json"
py -c "import json, os, pathlib; v=json.loads(pathlib.Path(os.environ['WORK']).joinpath('verify.json').read_text()); c=json.loads((pathlib.Path(os.environ['WS'])/'.runspecimen'/'runs'/os.environ['CAMPAIGN_ID']/os.environ['RUN_ID']/'certificate.json').read_text()); print('certificate_id', v.get('certificate_id')); print('event_chain', v.get('event_chain')); print('confirm_channel', v.get('confirm_channel')); print('approval_expires_at_unix', c.get('approval_expires_at_unix')); print('schema_version', c.get('schema_version')); print('live_ok', v.get('ok'))"
rs_ok N9-cert-fields $?
```

`verify` checks receipt integrity, the event chain, and live provenance. It
does not check HMAC or Ed25519 signatures. The `N9-cert-fields` lines must
show schema `2`, a `certificate_id`, the event-chain result, the bound
`confirm_channel`, `approval_expires_at_unix`, and `live_ok True`.

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
the pinned launcher template (`console_script_target` `runspecimen.cli:main`),
no unexpected files in `$VENV/bin`, `loaded_module_origins` from the real
launcher `doctor` process (each origin under stdlib or a hash-verified wheel
file), no bytecode under the installed package, `STEP N3-version exit=0`,
`STEP N3-verify exit=0`, and no import overrides
(`PYTHONPATH` / `PYTHONHOME` / `PYTHONSTARTUP` / `PYTHONPYCACHEPREFIX` unset,
`PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`,
no executable `.pth` import, no leftover setuptools shim, no sitecustomize
outside the interpreter stdlib).

N4–N7 use the same `rs` helper and the `CAMPAIGN_ID` / `RUN_ID` from N1.

N8 is a real human approval in a real terminal. An agent must not type `APPROVE`.

N9 is sequential `preflight`, `run`, `postflight`, `verify` with those same
identities, plus the schema-2 certificate field printout. `run` launches the
job with an explicit environment: bound `env_allowlist` values plus a
documented minimal set. Parent `PYTHONPATH` / `PYTHONHOME` are not inherited.

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

## Disposable N3-failure check (does not qualify the lifecycle)

A missing launcher at N3 must print `FAIL` and must not reach N4. That check
lives in the packed tests (`test_human_acceptance_n3_fails_when_launcher_is_missing`
and the zsh twin). Do not treat it as a substitute for N8 or N9.

## Non-approval default-vs-pretty supplement (does not qualify N8/N9)

Optional. Default JSON is the acceptance record. `--pretty` is human view
only. Do not use `--pretty` for N5–N7 or N9. After N5, this only checks that
`--pretty doctor` still exits 0. It does not replace N8 or N9.

```
rs --pretty --color never doctor --workspace "$WS"
rs_ok SUP-pretty-doctor $?
```

## Historical transcript (does not qualify this pack)

The original human transcript from an earlier session stays as-is. It used
hardcoded `demo-campaign` / `run-001` and a supplement that omitted N8/N9 on a
reused run ID. That omission cannot qualify this changed lifecycle. For this
pack, complete N1 through N10 and the schema-rejection check in one fresh
session with the `RUN_ID` exported above. Do not treat an N1–N7+N10-only paste
as acceptance of this pack.

```
Session: HUMAN-ACCEPTANCE historical note (not qualification)
Pack: artifacts/0.2.0rc15-2026-10-09-qafix13/
Do not paste N1–N7+N10 as a substitute for N8/N9 on this lifecycle.
```

A new N8 is a new approval. An agent must not type `APPROVE`.
