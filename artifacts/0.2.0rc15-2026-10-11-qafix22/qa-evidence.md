# QA evidence — unpublished 0.2.0rc15 qafix22

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-11-qafix22/`
Engine source: the PR #63 head that records this pack.
`src/` tree: `8468ab3c06b5f60cb2d7ca7a4bb15d64f76e3e36` (same tree as qafix14)
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

Prior pack `artifacts/0.2.0rc15-2026-10-11-qafix21/` was not modified.
qafix21 refused a `.pth` line with leading or trailing whitespace. This pack
refuses the whole file unless every byte is printable ASCII or a newline,
and it refuses a non-regular `.pth` before opening it.

The wheel bytes match qafix14 through qafix21 because the wheel is the engine
package. The sdist changed because the verifier, the tests, and the packed
docs changed.

## Pack bytes

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `f4111bc60fdda2d59d24b2aa9740fad5e3a27bcbeb49ba0018c5958ee8382d9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `5d3c0162b6784ca6d079fc28c2a104471387d9074c4599faad25bf007b45af78` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix21; does not embed the wheel) |
| `release-report.json` | `57174259ccd1e0f97ebbde6208f2678ca8b00bc73982e602178964ade4d47981` |
| `SHA256SUMS` | `2f2d8d60baf93473f2c2086173b42ee284e9a166199e554e63795561634aacc2` |

Toolchain: CPython 3.11.17, venv `/tmp/rs-relprep-qafix14` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two builds via `build_release_archives` / `build_plugin` were byte-identical
(`cmp`) for the wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`
before this directory was kept.

## Findings

| Finding | Fix | Tests |
| --- | --- | --- |
| RQ21-01 | A `.pth` file is read as raw bytes and refused unless every byte is printable ASCII (0x20–0x7E) or a newline. A CRLF pair is a newline. A byte-order mark is not stripped and is not accepted, so it cannot hide an `import` line or a directory name. | `test_rq2101_bom_import_is_refused`, `test_rq2101_bom_directory_is_refused` |
| RQ21-02 | The same byte rule refuses U+2028, U+2029, U+0085, `\x1c`, vertical tab, form feed, a lone CR, and a non-ASCII directory name before any line is split. `pyvenv.cfg` uses the same rule, except that `home`, `executable`, and `command` may contain ordinary non-ASCII path characters. | `test_rq2102_line_separators_are_refused`, `test_rq2102_lone_cr_is_refused`, `test_rq2102_non_ascii_directory_name_is_refused`, `test_pyvenv_allows_non_ascii_only_in_path_values` |
| RQ21-03 | A `.pth` file is `lstat`ed and opened with `O_NONBLOCK` and `O_NOFOLLOW`. `fstat` must also show a regular file. A FIFO is refused and is not read. A path named by a `.pth` line is treated the same way. | `test_rq2103_fifo_pth_is_refused`, `test_rq2103_fifo_path_entry_is_refused` |

`test_common_pth_bodies_follow_the_ascii_policy` checks that plain-ASCII `import` lines in `distutils-precedence.pth`, `_virtualenv.pth`, `__editable__*.pth`, `pywin32.pth`, and `matplotlib.pth` are still refused as executable imports. `test_verify_installed_wheel_rejects_missing_launcher` starts the checker with the base interpreter, and skips with a stated reason when that base cannot be named.

Each refusal test plants a canary (`SIDE-EFFECT`) that the planted code would write if it ran. The canary must be absent. The FIFO tests also bound the checker with a timeout.
