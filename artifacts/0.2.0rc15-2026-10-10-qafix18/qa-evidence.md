# QA evidence — unpublished 0.2.0rc15 qafix18

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-10-qafix18/`
Engine source: the PR #63 head that records this pack.
`src/` tree: `8468ab3c06b5f60cb2d7ca7a4bb15d64f76e3e36` (same tree as qafix14)
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

Prior packs `artifacts/0.2.0rc15-2026-10-10-qafix17/`,
`artifacts/0.2.0rc15-2026-10-10-qafix16/`,
`artifacts/0.2.0rc15-2026-10-10-qafix15/`, and
`artifacts/0.2.0rc15-2026-10-09-qafix14/` were not modified.

The wheel bytes match qafix14 through qafix17 because the wheel is the engine
package. The sdist changed because the verifier, the acceptance sheet text in
packed docs, and the tests changed.

## Pack bytes

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `f4111bc60fdda2d59d24b2aa9740fad5e3a27bcbeb49ba0018c5958ee8382d9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `e21176beceba50b9dd592a651e795a0f6ccecd655741c31143b0290b95925d17` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix17; does not embed the wheel) |
| `release-report.json` | `e596a0fe56aec6e71cd30a19de41ac37c5afddbbe89fa92702c91b0fa4cf7bc3` |
| `SHA256SUMS` | `4c35906aab89f2551f8a986edf6269d4b7014caa4dd6f57b3d395def6dbb9025` |

Toolchain: CPython 3.11.17, venv `/tmp/rs-relprep-qafix14` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two builds via `build_release_archives` / `build_plugin` were byte-identical
(`cmp`) for the wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`
before this directory was kept.

## Findings

| Finding | Fix | Tests |
| --- | --- | --- |
| RQ17-01 | The import-path scan does not stop after 64 directories. A path that does not exist is not counted. If more existing directories remain than the check can safely read, it refuses in plain English and does not run the environment. An unreadable `.pth` file, zip, or interpreter `sitecustomize`, and a venv Python link chain that is too long, are refused the same way. | `test_rq1701_eighty_pth_dirs_are_scanned_with_no_side_effect`, `test_rq1701_scan_limit_refuses_instead_of_dropping_paths`, `test_rq1701_missing_paths_do_not_consume_the_scan_limit`, `test_rq1701_too_many_interpreter_links_is_a_refusal` |
| RQ17-02 | The acceptance sheet records `python3` in `BASE_PY` before it creates the venv. `basepy` runs only that program. A wrapper, a symlink to a wrapper, or a byte copy at `bin/python` is not executed. | `test_rq1702_sheet_basepy_does_not_execute_venv_python` |
| RQ17-03 | `pyvenv.cfg` `home` and `executable` are compared by the real file they name, so a venv created through a symlink is accepted when that file is the Python running the check. | `test_rq1703_symlinked_interpreter_home_is_accepted` |
| RQ17-04 | A `.pth` file that is not UTF-8 text, or that contains a null byte, is a refusal in the usual JSON report. | `test_rq1704_nul_pth_is_a_json_refusal` |
| RQ17-05 | A `pyvenv.cfg` mismatch names that file. It is not reported as extra startup code. | `test_rq1705_home_mismatch_names_pyvenv_cfg` |

Each refusal test plants a canary (`SIDE-EFFECT`) that the planted code would write if it ran. The canary must be absent and `"ok"` must be false, except the symlink-home test, which is a clean accept (`"ok": true`). The 80-directory `.pth` names `d079/sitecustomize.py`. The sheet test runs `basepy` against a wrapper, a symlink to that wrapper, and a byte copy, in bash and zsh.
