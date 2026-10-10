# QA evidence — unpublished 0.2.0rc15 qafix20

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-10-qafix20/`
Engine source: the PR #63 head that records this pack.
`src/` tree: `8468ab3c06b5f60cb2d7ca7a4bb15d64f76e3e36` (same tree as qafix14)
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

Prior pack `artifacts/0.2.0rc15-2026-10-10-qafix19/` was not modified.
qafix19 is the symlink-home test fix. This pack changes the installed-wheel
verifier and the acceptance sheet.

The wheel bytes match qafix14 through qafix19 because the wheel is the engine
package. The sdist changed because the verifier, the tests, and the packed
docs changed.

## Pack bytes

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `f4111bc60fdda2d59d24b2aa9740fad5e3a27bcbeb49ba0018c5958ee8382d9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `bdf6bb811e7d589160543a46a9a1f2f1bb6e963c78b87450c841be26f09768e5` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix19; does not embed the wheel) |
| `release-report.json` | `f07773d6d1eebc5327568ea7932101b00099bfd0a2ebb6656a98c3c673e89932` |
| `SHA256SUMS` | `de8f24d408853985424fc0ae3167e1faa3b94fa293a8c82e9e23ddab2dadae9e` |

Toolchain: CPython 3.11.17, venv `/tmp/rs-relprep-qafix14` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two builds via `build_release_archives` / `build_plugin` were byte-identical
(`cmp`) for the wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`
before this directory was kept.

## Findings

| Finding | Fix | Tests |
| --- | --- | --- |
| RQ19-01 | The acceptance sheet starts the provenance check with `-I -S`. The check refuses when it was itself started by a virtual environment's Python. `pyvenv.cfg` is compared to the real path of the file that was started, not `sys._base_executable`. | `test_rq1901_venv_python_with_i_s_is_refused_and_canary_absent`, `test_rq1901_sheet_basepy_uses_i_s_so_venv_on_path_does_not_run_hooks` |
| RQ19-02 | A `.pth` line that names a path which exists but cannot be fully read is a refusal. A permission error, a non-regular file, and a file that is not a readable zip are not skipped. | `test_rq1902_unreadable_zip_on_pth_is_refused`, `test_rq1902_unreadable_directory_and_non_zip_file_are_refused` |
| P3a | A repeated `home` or `executable` in `pyvenv.cfg` is refused in plain English. This check does not guess which copy to keep. | `test_rq1903_duplicate_pyvenv_home_executable_is_refused` |
| P3b | A `.pth` line that names a symlink loop is a normal JSON refusal. | `test_rq1904_pth_symlink_loop_is_a_json_refusal` |
| P3c | `BASE_PY` is kept only when `python3` is an absolute path to a real program. The sheet then stores the real path that program reports with `-I -S`. A function, an alias, or a relative shim stops the sheet and is not executed. | `test_rq1905_sheet_does_not_run_a_python3_function_alias_or_relative_shim` |

Each refusal test plants a canary (`SIDE-EFFECT`) that the planted code would write if it ran. The canary must be absent. The duplicate-key test also starts the venv and checks that it still prints `123`. The unreadable-zip test restores mode `644` afterwards and checks that the file is then a zip containing `sitecustomize.py`.
