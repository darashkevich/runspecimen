# QA evidence — unpublished 0.2.0rc15 qafix21

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-11-qafix21/`
Engine source: the PR #63 head that records this pack.
`src/` tree: `8468ab3c06b5f60cb2d7ca7a4bb15d64f76e3e36` (same tree as qafix14)
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

Prior pack `artifacts/0.2.0rc15-2026-10-10-qafix20/` was not modified.
qafix20 is the venv-started checker and unreadable `.pth` path fix. This
pack changes how the installed-wheel verifier reads `.pth` lines.

The wheel bytes match qafix14 through qafix20 because the wheel is the engine
package. The sdist changed because the verifier, the tests, and the packed
docs changed.

## Pack bytes

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `f4111bc60fdda2d59d24b2aa9740fad5e3a27bcbeb49ba0018c5958ee8382d9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `042b45628d86eb8e4dfcdae0c824c5d1f74075bc15f6fe9dcd9cd988ab5878a8` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix20; does not embed the wheel) |
| `release-report.json` | `a3e0ad2f12a976d2d4615d45c11504c81787202082759829f819ed80dab011c7` |
| `SHA256SUMS` | `ea1f48158c96ca719b7a587e9c8532a6775de8c3cbe3f7a391c5ae761a421680` |

Toolchain: CPython 3.11.17, venv `/tmp/rs-relprep-qafix14` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two builds via `build_release_archives` / `build_plugin` were byte-identical
(`cmp`) for the wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`
before this directory was kept.

## Findings

| Finding | Fix | Tests |
| --- | --- | --- |
| RQ20-01 | A `.pth` line with leading or trailing whitespace, or a control character, is refused in plain English. The line is not stripped and then read as a different directory. CPython keeps a leading space as part of the directory name (`site.addpackage` only `rstrip`s). Comment lines that start with `#` and have no extra whitespace are still skipped. `pyvenv.cfg` is split on universal newlines and then stripped the same way `site.venv` strips keys and values. `sitecustomize` import names come from the parse tree. | `test_rq2001_leading_space_pth_refuses_apport_chain`, `test_rq2001_leading_tab_pth_is_refused`, `test_rq2001_trailing_spaces_pth_is_refused`, `test_rq2001_mixed_crlf_pth_is_refused` |

The leading-space test plants `sitecustomize.py` and `apport_python_hook.py` in a directory whose name starts with a space, and an empty decoy directory without that space. Each refusal test plants a canary (`SIDE-EFFECT`) that the planted code would write if it ran. The canary must be absent, and the JSON message must say the line has whitespace. The trailing-space test puts the canary in the directory CPython would add after `rstrip`. The mixed-CRLF test also plants a control character in a later line.
