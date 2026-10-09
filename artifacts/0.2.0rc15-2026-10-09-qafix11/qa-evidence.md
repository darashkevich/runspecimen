# QA evidence — unpublished 0.2.0rc15 qafix11

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-09-qafix11/`
Engine source: PR #63 commit `9377ea2e23122d67ddd8bc5041160dc772719585`
(𝜋thon allowlist plus macOS stdlib-root resolve; `src/` tree unchanged from `55f0781`).
`src/` tree: `019fff590c315299bbb12c243cfb8182f0cedfc1`
`src/` archive SHA-256 (`git archive HEAD:src | sha256sum`):
`607c973e3e241146f6d25ea355e8838cb729e0c22c1bb0a5888dde20c1578484`
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

This same-round qafix11 pack replaces the premature archive files recorded
at `5682b11` (CC-01..CC-06 without WH-01..04). qafix10
(`artifacts/0.2.0rc15-2026-10-08-qafix10/`) was not overwritten. The
qafix12 snapshot (`artifacts/0.2.0rc15-2026-10-09-qafix12/`) stays on disk
and is not the golden pack. Packed tests pin only the qafix11 directory
name; archive hashes live in this unpacked pack and in CANDIDATE_MANIFEST /
QUALIFICATION_CHECKLIST / READINESS_LEDGER.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `fb1a1fca5c1cbc10c9c448d3803f2d9fc9ba000778bd4e30762d06fed56aaac3` |
| `runspecimen-0.2.0rc15.tar.gz` | `d0174ba8d6fb3599cbc458a69af129b5f5336ce25f0ef172d425d82c589fdee1` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix10; does not embed the wheel) |
| `release-report.json` | `434ee1d10da7cbfccfdec521c323000e7334902e8ceb733c6232ae85f1a597f8` |
| `SHA256SUMS` | `95449a880a8f2106fb69ac264ab9a35f7747094a641b0ed234c67af7e8cf2986` |

Toolchain: CPython 3.12.3, venv `/tmp/rs-relprep-qafix5` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two independent rebuilds (`/tmp/rs-qafix11-pack2-a-2n_v9aoq` and
`/tmp/rs-qafix11-pack2-b-3f143sw5`) were byte-identical (`cmp`) for wheel,
sdist, plugin zip, `release-report.json`, and `SHA256SUMS`.

This pack is ChatGPT QA #5 plus WH-01..04 (DO-NOT-SHIP): CC-01..CC-06,
CC-04 pip 25/26 console-script bodies, WH-01..04.

## 1. Full skip list from local unittest

Command: `PYTHONPATH=src /tmp/rs-relprep-qafix5/bin/python -m unittest discover -s tests -v`
Result: **795 tests, skipped=78, 0 failed**.
Unittest wall time: **201.536s** (cap 600s). Golden rebuild printed
`reproducible sdist d0174ba8…` / `reproducible wheel fb1a1fca…`.
Skip list is unchanged from qafix10 (78 Linux skips).

`src/` is unchanged from `55f0781` (**wheel `fb1a1fca…` unchanged**).
Plugin `ea38d5bc…` is unchanged. Sdist is `d0174ba8…` because packed
`scripts/verify_installed_wheel.py`, tests, and CHANGELOG gained the CPython
3.14 `𝜋thon` allowlist and macOS stdlib-root `resolve()`. Test count is 795
because this pass adds `tests/test_qafix11_wh.py`.

The 78 Linux skips are Darwin-only or host-specific (CryptoKit, P-256
verifier, phone peer, rsync/holder stage, codesign, sandbox-exec, relocatable
Mach-O) plus PyNaCl and pytest. None was turned into a passing stand-in.

## 2. Darwin 3.11 unittest timings

Local pack unittest discover: **201.536s** vs 600s cap.
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
| CC-01 | Refuse at `contract.py` (`_refuse_display_controls` on argv and on other contract strings via `_require_str`). Escape on display (`present.py` `_scalar`, approve review, errors, pretty). | `test_n10_and_unknown_field_error_bytes_unchanged`, `test_bind_line_unchanged_when_argv_is_escaped`, `test_rendered_bytes_escape_esc_csi_osc_cr_bs_bidi_nul`, `test_contract_refuses_controls_in_argv_cwd_env_and_ids`, `test_unsafe_classifier_and_escape` |
| CC-02 | Shebang parent DIRECTORIES compared with `Path.samefile`, not lexical paths and not interpreter realpath. | `test_cc02_default_tmpdir_venv_shebang_is_accepted`, `test_cc02_symlinked_parent_dirs_are_accepted`, `test_cc02_other_venv_sharing_base_python_is_refused` |
| CC-03 | Pretty `verify-signature` leads with `Receipt error` / `receipt_verification_error` when `ok` is false. Default JSON unchanged. | `test_pretty_mac_valid_receipt_invalid_leads_with_receipt_error`, `test_cli_pretty_verify_signature_missing_state_shows_explanatory_text` |
| CC-04 | Launcher body after the shebang must byte-match one of three exact pinned pip templates for `runspecimen.cli:main`. No regex. | `test_pinned_templates_are_exact_known_bodies`, `test_pinned_template_matches_real_pip_body`, `test_import_main_without_calling_it_is_refused` |
| CC-05 | Verifier refuses any `.pyc` / `__pycache__` under the installed package, `PYTHONPYCACHEPREFIX` / `sys.pycache_prefix`, and sourceless bytecode. Probe `-I -B`. Sheet: `pip install --no-compile` and `PYTHONDONTWRITEBYTECODE=1`. | `test_timestamp_pyc_under_package_is_refused`, `test_hash_based_pyc_under_package_is_refused`, `test_pythonpycacheprefix_is_refused` |
| CC-06 | Signing copy no longer implies that signing prevents a forged approval or an execution. Schema 1 is not called “rejected”; legacy receipts without a bound approval fail verify. A bound approval event is not cryptographic proof of a human. | `test_protect_against_that_sign_receipts_is_gone`, `test_signing_limit_wording_is_present` |

Pinned launcher bodies (shebang validated separately):

1) distlib `SCRIPT_TEMPLATE` (195 bytes). pip 21.2.4 on macOS system CPython
3.9.6 ensurepip; pip 24.x on GHA 3.9–3.12. Captured from pip 24.0 on this
pack host (CPython 3.12.3). RECORD length includes shebang (238 bytes here).

```
# -*- coding: utf-8 -*-
import re
import sys
from runspecimen.cli import main
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(main())
```

2) pip 25.1–25.3 PipScriptMaker (`endswith('.exe')` then `[:-4]`; 168 bytes).

```
import sys
from runspecimen.cli import main
if __name__ == '__main__':
    if sys.argv[0].endswith('.exe'):
        sys.argv[0] = sys.argv[0][:-4]
    sys.exit(main())
```

3) pip 26.0+ PipScriptMaker (`removesuffix('.exe')`; 143-byte body). GHA
ubuntu 3.13, ubuntu 3.14, macos 3.14. RECORD length ~186 bytes including
shebang.

```
import sys
from runspecimen.cli import main
if __name__ == '__main__':
    sys.argv[0] = sys.argv[0].removesuffix('.exe')
    sys.exit(main())
```

## 4. WH-01..04

| Finding | Fix | Tests |
| --- | --- | --- |
| WH-01 | Verifier refuses unexpected `venv/bin` files (`.py` / `.pyc` / `.so` / directories). Provenance probes the real `runspecimen doctor` process (`loaded_module_origins`); `__main__` may be the launcher; Debian sitecustomize outside the venv is interpreter-owned. Sheet invokes `$RS` only; `python -m runspecimen` from an untrusted cwd is not a supported verified path. | `test_wh01_bin_json_py_is_refused`, `test_wh01_bin_directory_and_pyc_are_refused`, `test_wh01_bin_allowlist_includes_versioned_python_and_pip`, `test_wh01_doctor_json_includes_loaded_module_origins`, `test_wh01_doctor_origin_allowlist_accepts_launcher_main_and_distro_sitecustomize`, `test_wh01_human_acceptance_does_not_invoke_minus_m_runspecimen`, `test_qa_hooks_03_clean_sheet_venv_is_accepted` |
| WH-02 | Shared `escape_for_terminal` on every terminal-bound string (approve cwd/outputs, pretty errors/status/doctor, `confirm_channel_note`). `_require_str` refuses control/bidi. Refuse at validation AND escape on display. | `test_wh02_require_str_refuses_controls_with_plain_english`, `test_wh02_approve_cwd_outputs_escape_cr_osc_csi`, `test_wh02_pretty_error_status_doctor_confirm_note_escape`, `test_wh02_nul_still_refused_at_contract` |
| WH-03 | Job `Popen` uses an explicit env from bound `env_allowlist` plus `MINIMAL_JOB_ENV_NAMES`. Parent `PYTHONPATH` / `PYTHONHOME` are not inherited. Run refuses allowlist drift. Behaviour change. | `test_wh03_parent_pythonpath_does_not_reach_the_job`, `test_wh03_allowlisted_env_drift_is_refused`, `test_wh03_job_environment_refuses_hash_drift`, `test_wh03_allowlisted_value_is_passed_and_python_star_not_in_minimal_set` |
| WH-04 | Refuse a symlinked `.runspecimen`, campaign, or run dir (and symlinked control-plane components). Writes use no-follow semantics where available. | `test_wh04_symlinked_runspecimen_is_refused_on_approve`, `test_wh04_symlinked_run_dir_is_refused`, `test_wh04_symlinked_campaign_dir_is_refused_on_run_state` |

## 5. HUMAN-ACCEPTANCE sheet

Exact new setup lines:

```
export PACK="$PWD/artifacts/0.2.0rc15-2026-10-09-qafix11"
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
python3 -m venv "$VENV"
"$PY" -m pip uninstall -y setuptools
py -m pip install --no-index --no-deps --force-reinstall --no-compile "$WHEEL"
```

Record at top of notes: Candidate SHA (`git rev-parse HEAD`), pack path,
shell/Python identities, and the N2 `wheel_sha256` (full 64 hex chars).
`CAMPAIGN_ID` / `RUN_ID` are set once in N1 and rewritten into the demo
contract at N4-ids. N3 covers launcher-template and no-bytecode checks.
N9 prints schema-2 certificate fields (`certificate_id`, event-chain,
bound `confirm_channel`, expiry, live provenance). The historical
N1–N7+N10 supplement cannot qualify this lifecycle. N10 and the
unknown-field line stay byte-exact. Default JSON is the main session;
`--pretty doctor` is a non-qualifying supplement. Doctor JSON may include
`loaded_module_origins`.

Automated sheet: `test_human_acceptance_sheet_n1_n7_n10_unk_in_bash` ok
(skips N8/N9 as designed; no APPROVE). N3 missing-launcher stop ok.

## 6. Guardrail checks

| Gate | State |
| --- | --- |
| `run_integration_complete` | false |
| `e2_closed` | false |
| D1 installed admission | fail-closed |
| D2 `production_verifier_pin()` | unchanged |
| N10 | `execution policy local has no typed-phrase fallback` (byte-exact) |
| unknown-field | `contract contains unknown field(s): not_a_real_contract_field` (byte-exact) |
| default CLI JSON | unchanged except `doctor` may include `loaded_module_origins` |
| MAS bind line | `Type 'APPROVE' to bind this approval:` |
| APPROVE phrase | not typed |
| `--human-invoked` | not used |
| merge / publish / retag / notarize / real-machine install | not done |
| older packs | qafix10 and earlier stay on disk; qafix11 archives replaced in this same-round completion |
