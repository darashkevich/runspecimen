# QA evidence — unpublished 0.2.0rc15 qafix16

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-10-qafix16/`
Engine source: the PR #63 head that records this pack.
`src/` tree: `8468ab3c06b5f60cb2d7ca7a4bb15d64f76e3e36` (same tree as qafix14)
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`

Prior packs `artifacts/0.2.0rc15-2026-10-10-qafix15/` and
`artifacts/0.2.0rc15-2026-10-09-qafix14/` were not modified.
qafix15 has the same verifier. Its provenance test resolved `bin/python`
after the plant. On Python 3.9 and 3.10, `pyvenv.cfg` has no `executable`
key, so that walk started the verifier through the planted wrapper.
qafix16 resolves the base interpreter first.

The wheel bytes match qafix14 and qafix15 because the wheel is the engine
package. The sdist changed because the test and the packed docs changed.

## Pack bytes

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `f4111bc60fdda2d59d24b2aa9740fad5e3a27bcbeb49ba0018c5958ee8382d9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `23e2dbf2dac5561a0462927dd1f09f413c6276ada4d0be74d607d159a03f316b` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged from qafix through qafix15; does not embed the wheel) |
| `release-report.json` | `dfeddb707d7024f7a2fd8ba4c21ae9006f39cdd6ebfcf7cf4461a312dd445322` |
| `SHA256SUMS` | `d9bf18dbe0dc9bf2854f5ffcbac8241d4ec71b6906d9cdd72cbc53772c47bacf` |

Toolchain: CPython 3.11.17, venv `/tmp/rs-relprep-qafix14` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two builds via `build_release_archives` / `build_plugin` were byte-identical
(`cmp`) for the wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`
before this directory was kept.

## Findings

| Finding | Fix | Tests |
| --- | --- | --- |
| RQ14-01 | Every venv interpreter entry (`python`, `python3`, `python3.X`, `𝜋thon`) must be a symlink to the base interpreter named by `pyvenv.cfg`, or a byte-for-byte copy. Anything else is refused before a probe. Probes run on that base interpreter. | `test_rq1401_python_wrapper_is_refused_with_no_side_effect` |
| RQ14-02 | `.pth` path lines, including folders and zips, are followed and scanned for startup hooks. Debian's `sitecustomize` import chain is read and not executed; the probe uses `-S`. | `test_rq1402_pth_directory_and_zip_sitecustomize_have_no_side_effect` |
| RQ14-03 | `sitecustomize` and `usercustomize` are scanned with importlib's source, bytecode, and extension suffixes, including packages and `__pycache__`. | `test_rq1403_extension_and_sourceless_pyc_hooks_have_no_side_effect` |
| RQ14-04 | Turning on system site-packages names the `pyvenv.cfg` path in the refusal. | `test_rq1404_include_system_site_packages_message_names_pyvenv_cfg` |

Each refusal test plants a canary (`SIDE-EFFECT`) that the planted code would write if it ran. The canary must be absent and `"ok"` must be false. The harness resolves the base interpreter before the plant, including on Python 3.9 and 3.10.

A clean sheet-prepared venv is still accepted (`test_qa_hooks_03_clean_sheet_venv_is_accepted`).
