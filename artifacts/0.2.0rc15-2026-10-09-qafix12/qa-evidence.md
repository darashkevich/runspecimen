# QA evidence — unpublished 0.2.0rc15 qafix12

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-09-qafix12/`
Engine source: PR #63 commit `882415b773f608d185d9468299f02debb1bbd6a6`
(the src+tests+docs commit; this pack commit does not change `src/`).
`src/` tree: `f263d414dad20624b395e2b3a398e2d9ff150c57` (unchanged from qafix11)
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

qafix11 (`artifacts/0.2.0rc15-2026-10-09-qafix11/`) was not overwritten.
qafix10 (`artifacts/0.2.0rc15-2026-10-08-qafix10/`) was not overwritten.
Packed tests pin only the qafix12 directory name; archive hashes live in
this unpacked pack and in CANDIDATE_MANIFEST / QUALIFICATION_CHECKLIST /
READINESS_LEDGER / HUMAN_DEVICE_KIT.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `72503166a31bc15bda8e31cfb57820ce7111355b3798e6fcdd53ce2c83a56ca4` (byte-identical to qafix11; `src/` unchanged) |
| `runspecimen-0.2.0rc15.tar.gz` | `8ecf72a9993b9dd5700ba9929e51d386d4c114833f3eacc4e1c963575055801c` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix11; does not embed the wheel) |
| `release-report.json` | `3d3c3396bde7fb360a5d7f76a5f76d3400cae537ad4cacc22053493720c55725` |
| `SHA256SUMS` | `8ace79fec889e5c2e6f7bed63e42a5b82d2b782f442a93db27f30e9d19224883` |

Toolchain: CPython 3.12.3, venv `/tmp/rs-relprep-qafix5` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two independent rebuilds (`/tmp/rs-qafix12-a` and `/tmp/rs-qafix12-b`) were
byte-identical (`cmp`) for wheel, sdist, plugin zip, `release-report.json`,
and `SHA256SUMS`.

This pack is ChatGPT QA #5 (DO-NOT-SHIP) CC-04 follow-up: pin the exact pip
25/26 console-script bodies so CPython 3.13/3.14 GHA ensurepip is accepted.
CC-01..CC-06 and HUMAN-ACCEPTANCE from qafix11 stay in force.

## 1. Full skip list from local `release_check.py`

Command: `/tmp/rs-relprep-qafix5/bin/python scripts/release_check.py --output-dir /tmp/rs-qafix12-a`
Result: **777 tests, skipped=78, 0 failed**, then 4/4 distribution tests, exit 0.
Unittest wall time: **193.623s** (cap 600s). Second rebuild: 777 tests, skipped=78,
197.269s, then 4/4, exit 0. Skip list is unchanged from qafix11.

Wheel `72503166…` is byte-identical to qafix11. Plugin `ea38d5bc…` is unchanged.
Sdist is `8ecf72a9…` because packed `scripts/verify_installed_wheel.py`, tests,
and packed CHANGELOG/RELEASE_CANDIDATE_REPORT changed. Test count rose from
776 to 777 because `test_pinned_templates_are_exact_known_bodies` was added.

The 78 Linux skips are Darwin-only or host-specific (CryptoKit, P-256
verifier, phone peer, rsync/holder stage, codesign, sandbox-exec, relocatable
Mach-O) plus PyNaCl and pytest. None was turned into a passing stand-in.
The named skip table is the same 78 rows as
`artifacts/0.2.0rc15-2026-10-09-qafix11/qa-evidence.md`.

## 2. Darwin 3.11 unittest timings

Local pack unittest discover: **193.623s** vs 600s cap (second rebuild 197.269s).
Report Darwin 3.11 timings from the unittest line `Ran N tests in X s` in the
CI logs, **not** the GitHub Actions job wall clock.

qafix11 Darwin 3.11 (HEAD `5682b11`, job 113835575318): `Ran 776 tests in 385.472s`.

## 3. CC-01..CC-06

CC-01 dual approach (documented in `src/runspecimen/terminaltext.py` and
`src/runspecimen/contract.py`): refuse C0/C1/DEL/bidi/format characters at
contract validation, **and** escape them on every TTY display path. The bind
line stays `Type 'APPROVE' to bind this approval:`. N10 and unknown-field
error bytes stay exact.

| Finding | Fix | Tests |
| --- | --- | --- |
| CC-01 | Refuse at `contract.py` (`_refuse_display_controls` on argv at the preferred point, and on other contract/workspace strings via `_require_str`). Escape on display (`present.py` `_scalar`, approve review, errors, pretty). | `test_n10_and_unknown_field_error_bytes_unchanged`, `test_bind_line_unchanged_when_argv_is_escaped`, `test_rendered_bytes_escape_esc_csi_osc_cr_bs_bidi_nul`, `test_contract_refuses_controls_in_argv_cwd_env_and_ids`, `test_unsafe_classifier_and_escape` |
| CC-02 | Shebang parent DIRECTORIES compared with `Path.samefile`, not lexical paths and not interpreter realpath. | `test_cc02_default_tmpdir_venv_shebang_is_accepted`, `test_cc02_symlinked_parent_dirs_are_accepted`, `test_cc02_other_venv_sharing_base_python_is_refused` |
| CC-03 | Pretty `verify-signature` leads with `Receipt error` / `receipt_verification_error` when `ok` is false. Default JSON unchanged. | `test_pretty_mac_valid_receipt_invalid_leads_with_receipt_error`, `test_cli_pretty_verify_signature_missing_state_shows_explanatory_text` |
| CC-04 | Launcher body after the shebang must byte-match one of the pinned exact pip templates for `runspecimen.cli:main`. No regex. | `test_pinned_templates_are_exact_known_bodies`, `test_pinned_template_matches_real_pip_body`, `test_import_main_without_calling_it_is_refused` |
| CC-05 | Verifier refuses any `.pyc` / `__pycache__` under the installed package, `PYTHONPYCACHEPREFIX` / `sys.pycache_prefix`, and sourceless bytecode. Probe `-I -B`. Sheet: `pip install --no-compile` and `PYTHONDONTWRITEBYTECODE=1`. | `test_timestamp_pyc_under_package_is_refused`, `test_hash_based_pyc_under_package_is_refused`, `test_pythonpycacheprefix_is_refused` |
| CC-06 | Signing copy no longer implies that signing prevents a forged approval or an execution. Schema 1 is not called “rejected”; legacy receipts without a bound approval fail verify. A bound approval event is not cryptographic proof of a human. | `test_protect_against_that_sign_receipts_is_gone`, `test_signing_limit_wording_is_present` |

Pinned launcher bodies (shebang validated separately). Only these exact
byte strings are accepted.

**1. distlib `SCRIPT_TEMPLATE`** — pip 21.2.4 (macOS 12+ system CPython 3.9.6
ensurepip); pip 24.x on GHA 3.9 / 3.10 / 3.11 / 3.12. Captured from pip 24.0
on this pack host (CPython 3.12.3) and from those GHA jobs.

```
# -*- coding: utf-8 -*-
import re
import sys
from runspecimen.cli import main
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(main())
```

**2. pip 25.1–25.3 PipScriptMaker** (`pip/_internal/operations/install/wheel.py`,
PR #13166). Exact `textwrap.dedent` of that template. Not emitted by current
GHA 3.9–3.12 (those write (1)) or GHA 3.13/3.14 (those write (3)).

```
import sys
from runspecimen.cli import main
if __name__ == '__main__':
    if sys.argv[0].endswith('.exe'):
        sys.argv[0] = sys.argv[0][:-4]
    sys.exit(main())
```

**3. pip 26.0+ PipScriptMaker** (PR #13697, `.removesuffix('.exe')`). Captured
from GHA ubuntu 3.13, ubuntu 3.14, and macos 3.14: unittest shortening of the
installed 143-byte body matches this value exactly and does not match (1) or (2).

```
import sys
from runspecimen.cli import main
if __name__ == '__main__':
    sys.argv[0] = sys.argv[0].removesuffix('.exe')
    sys.exit(main())
```

## 4. HUMAN-ACCEPTANCE sheet

Exact new setup lines:

```
python3 -m venv "$VENV"
"$PY" -m pip uninstall -y setuptools
rs() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 "$RS" "$@"; }
py() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 "$PY" "$@"; }
py -m pip install --no-index --no-deps --force-reinstall --no-compile "$WHEEL"
```

`CAMPAIGN_ID` / `RUN_ID` are set once in N1 (`RUN_ID="ha-$(date +%Y%m%d-%H%M%S)-$$"`)
and rewritten into the demo contract at N4-ids. N9 prints schema-2 certificate
fields. The historical N1–N7+N10 supplement cannot qualify this lifecycle.
N10 and the unknown-field line stay byte-exact. Default JSON is the main
session; `--pretty doctor` is a non-qualifying supplement.

## 5. Guardrail checks

| Gate | State |
| --- | --- |
| `run_integration_complete` | false |
| `e2_closed` | false |
| D1 installed admission | fail-closed |
| D2 `production_verifier_pin()` | unchanged |
| N10 | `execution policy local has no typed-phrase fallback` (byte-exact) |
| unknown-field | `contract contains unknown field(s): not_a_real_contract_field` (byte-exact) |
| default CLI JSON | unchanged (except `about` honesty, already in qafix10) |
| MAS bind line | `Type 'APPROVE' to bind this approval:` |
| APPROVE phrase | not typed |
| `--human-invoked` | not used |
| merge / publish / retag / notarize / real-machine install | not done |
| older packs | not overwritten (qafix11, qafix10, and earlier stay on disk) |
