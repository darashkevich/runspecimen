# QA evidence — unpublished 0.2.0rc15 qafix14

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-09-qafix14/`
Engine source: the PR #63 head that records this pack.
`src/` tree: `8468ab3c06b5f60cb2d7ca7a4bb15d64f76e3e36`
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

Prior pack `artifacts/0.2.0rc15-2026-10-09-qafix13/` was not modified.
`src/` changed (event log, lock opens, snapshot streaming). The qafix13
wheel `fb1a1fca…` stays the record of that earlier tree
(`019fff590c315299bbb12c243cfb8182f0cedfc1`).

## Pack bytes

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `f4111bc60fdda2d59d24b2aa9740fad5e3a27bcbeb49ba0018c5958ee8382d9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `804468f04182e3b1c354c1c4eb323a378b0ff9f44a9d28dd8181be5f850aa527` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix13; does not embed the wheel) |
| `release-report.json` | `1aa131691eb801c4ead1357d7f7e92a595bc0a17f1eb2f1b4be448744f144c42` |
| `SHA256SUMS` | `1e238423ed497a690a1c9f87ba63ae028531586855ae812d0086deb407019c5d` |

Toolchain: CPython 3.11.17, venv `/tmp/rs-relprep-qafix14` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two builds via `build_release_archives` / `build_plugin` were byte-identical
(`cmp`) for the wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`
before this directory was kept.

## Findings

| Finding | Fix | Tests |
| --- | --- | --- |
| LATEST-01 | Static scan refuses `sitecustomize` and `usercustomize` as a module or a package before any venv file runs. | `test_latest01_sitecustomize_package_is_refused_with_no_side_effect`, `test_latest01_usercustomize_package_is_refused_with_no_side_effect` |
| LATEST-02 | A launcher that is not a pinned pip template is refused before it is executed. | `test_latest02_tampered_launcher_is_not_executed` |
| LATEST-03 | The first event-log create happens under the append lock, so two first writers get sequences 1 and 2 and neither sees `FileExistsError`. | `test_latest03_concurrent_first_append_assigns_seq_1_and_2` |
| LATEST-04 | Lock, state, and approval files are opened with no-follow checks. A symlink is refused. | `test_latest04_event_append_lock_symlink_is_refused`, `test_latest04_lease_lock_symlink_is_refused`, `test_latest04_lease_meta_symlink_is_refused`, `test_latest04_keys_lock_symlink_is_refused`, `test_latest04_holder_op_lock_symlink_is_refused`, `test_latest04_state_and_approval_symlinks_are_refused` |
| LATEST-05 | The default-TMPDIR shebang check calls `samefile` while the temporary venv still exists. | `test_cc02_default_tmpdir_venv_shebang_is_accepted` |
| SIB-01 | Debian `dist-packages` directories under the venv are scanned, and they are excluded from the standard library. | `test_sib01_debian_dist_packages_pth_and_module_have_no_side_effect`, `test_sib01_dist_packages_module_alone_is_refused_with_no_side_effect` |
| SIB-02 | An executable `.pth` in site-packages is refused before the venv Python runs. The check is started with the base interpreter and `-I`. | `test_sib02_site_packages_pth_is_refused_with_no_side_effect` |
| STRUCT-02 | Snapshot bytes are hashed while they are copied. Only a bounded shebang prefix is kept. A shebang line longer than 4096 bytes with no newline is refused. | `test_large_input_snapshot_peak_stays_under_half_the_input`, `test_snapshot_bytes_and_fingerprints_match_the_rebind_helper` |

Marker files named `SIDE-EFFECT` must not be created by those refusal tests.
A clean sheet-prepared venv is still accepted (`test_qa_hooks_03_clean_sheet_venv_is_accepted`, and the bash/zsh sheet replay of N1–N7, N10, and the unknown-field check).

## Local unittest

CPython 3.12.3: `Ran 810 tests in 205.193s`, skipped 78. The only error was
`test_wheel_and_sdist_digests_repeat` on the system interpreter, which does
not have setuptools>=77. The same test passes with the 3.11.17 pack venv
(setuptools 84.0.0, wheel 0.48.0). Skip list is unchanged from qafix13.
Darwin 3.11 `Ran N tests in X s` is taken from CI logs, not from a job clock.

## Guardrails

| Gate | State |
| --- | --- |
| `run_integration_complete` | false |
| `e2_closed` | false |
| D1 installed admission | fail-closed |
| D2 `production_verifier_pin()` | unchanged |
| N10 | `execution policy local has no typed-phrase fallback` (byte-exact) |
| unknown-field | `contract contains unknown field(s): not_a_real_contract_field` (byte-exact) |
| default CLI JSON | unchanged except `doctor` may include `loaded_module_origins` |
| APPROVE / `--human-invoked` | not used |
| merge / publish / retag | not done |
| older packs | qafix13 and earlier stay on disk unmodified |
