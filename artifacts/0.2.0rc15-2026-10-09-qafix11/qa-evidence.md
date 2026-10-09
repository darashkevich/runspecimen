# QA evidence — unpublished 0.2.0rc15 qafix11

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-09-qafix11/`
Engine source: PR #63 commit `400dba072e24f08c949f3b23c28405ada424cedd`
(the src+tests+docs commit; this pack commit does not change `src/`).
`src/` tree: `f263d414dad20624b395e2b3a398e2d9ff150c57`
`src/` archive SHA-256 (`git archive HEAD:src | sha256sum`):
`4836421e720c04708cade94ba007821b180d1b44ad0bad780e07ef172bb5c37c`
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

qafix10 (`artifacts/0.2.0rc15-2026-10-08-qafix10/`) was not overwritten.
That in-place sdist correction is historical. Packed tests pin only the
qafix11 directory name; archive hashes live in this unpacked pack and in
CANDIDATE_MANIFEST / QUALIFICATION_CHECKLIST / READINESS_LEDGER.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `72503166a31bc15bda8e31cfb57820ce7111355b3798e6fcdd53ce2c83a56ca4` |
| `runspecimen-0.2.0rc15.tar.gz` | `74de1e7d1a06092a419678f2912968ccb81f8614775135f8257294963f036bb7` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix10; does not embed the wheel) |
| `release-report.json` | `a4fb01bdc70bf23adbb5ccbfbf112786e3dc2070e53943b3f10ebd514d8e7253` |

Toolchain: CPython 3.12.3, venv `/tmp/rs-relprep-qafix5` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two independent rebuilds (`/tmp/rs-qafix11-a` and `/tmp/rs-qafix11-b`) were
byte-identical (`cmp`) for wheel, sdist, plugin zip, `release-report.json`,
and `SHA256SUMS`.

This pack is ChatGPT QA #5 (DO-NOT-SHIP): CC-01..CC-06 plus HUMAN-ACCEPTANCE.

## 1. Full skip list from local `release_check.py`

Command: `/tmp/rs-relprep-qafix5/bin/python scripts/release_check.py --output-dir /tmp/rs-qafix11-a`
Result: **776 tests, skipped=78, 0 failed**, then 4/4 distribution tests, exit 0.
Unittest wall time: **191.326s** (cap 600s). Second rebuild: 776 tests, skipped=78,
190.354s, then 4/4, exit 0. Skip list is unchanged from qafix10.

`src/` changed (CC-01..CC-06), so **wheel `72503166…` is new**.
Plugin `ea38d5bc…` is unchanged. Sdist is `74de1e7d…` because packed
`scripts/verify_installed_wheel.py`, `src/runspecimen/*`, tests, and packed
docs/CHANGELOG changed. Test count rose from 759 to 776 because this pass
adds `tests/test_qafix11_cc.py`.

The 78 Linux skips are Darwin-only or host-specific (CryptoKit, P-256
verifier, phone peer, rsync/holder stage, codesign, sandbox-exec, relocatable
Mach-O) plus PyNaCl and pytest. None was turned into a passing stand-in.
The named skip table is the same 78 rows as
`artifacts/0.2.0rc15-2026-10-08-qafix10/qa-evidence.md`.

## 2. Darwin 3.11 unittest timings

Local pack unittest discover: **191.326s** vs 600s cap (second rebuild 190.354s).
Report Darwin 3.11 timings from the unittest line `Ran N tests in X s` in the
CI logs, **not** the GitHub Actions job wall clock.

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
| CC-04 | Launcher body after the shebang must byte-match the pinned pip distlib `SCRIPT_TEMPLATE` for `runspecimen.cli:main`. No regex. | `test_pinned_template_matches_real_pip_body`, `test_import_main_without_calling_it_is_refused` |
| CC-05 | Verifier refuses any `.pyc` / `__pycache__` under the installed package, `PYTHONPYCACHEPREFIX` / `sys.pycache_prefix`, and sourceless bytecode. Probe `-I -B`. Sheet: `pip install --no-compile` and `PYTHONDONTWRITEBYTECODE=1`. | `test_timestamp_pyc_under_package_is_refused`, `test_hash_based_pyc_under_package_is_refused`, `test_pythonpycacheprefix_is_refused` |
| CC-06 | Signing copy no longer implies that signing prevents a forged approval or an execution. Schema 1 is not called “rejected”; legacy receipts without a bound approval fail verify. A bound approval event is not cryptographic proof of a human. | `test_protect_against_that_sign_receipts_is_gone`, `test_signing_limit_wording_is_present` |

Pinned launcher body (pip 21.2.4 on macOS system CPython 3.9.6 ensurepip;
pip 24.0 / 24.x / 25.x on CPython 3.12 / 3.13 / 3.14; captured from pip 24.0
on this pack host). Shebang validated separately:

```
# -*- coding: utf-8 -*-
import re
import sys
from runspecimen.cli import main
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
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

Automated sheet: `test_human_acceptance_sheet_n1_n7_n10_unk_in_bash` ok
(skips N8/N9 as designed; no APPROVE). N3 missing-launcher stop ok.

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
| older packs | not overwritten (qafix10 and earlier stay on disk) |
