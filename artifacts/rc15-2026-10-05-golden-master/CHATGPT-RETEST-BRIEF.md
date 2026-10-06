# ChatGPT retest brief — PR #39 engineering GM

Working tip: `cursor/evidence-expansion-coherence` after #39/`e2a3216`, #47/`329e08b`, #49/`18ef461`. `cursor/integrated-release-candidate` is historical at `a0dc233`. NEW-01 package-tree SHA `5f35cfcf401107648d61b84e29da5a2e8b45f708`. Prior pack-recording SHA `0fcfc8f6c39c359a153a81d08cd048280ece5e08`. OPEN-SDIST regenerated the sdist to `316938cea04f6747e32fd88f263533d710d489861fc36372c897680088fd63d3`; wheel and plugin hashes are unchanged. Pack `artifacts/rc15-2026-10-05-golden-master/`. Canonical hashes: `docs/CANDIDATE_MANIFEST.md`.

**Locked.** D1: installed admission fail-closed; E2 open; `run_integration_complete` and `e2_closed` false; no SE invention. D2: holder id `com.darashkevich.runspecimen.holder` accepted; no rename.

**Since `6bb64d1`:** NEW-01 only (plus docs/pack). Sandbox `top_level` now wins on `sys.path` over the live workspace for packaged unittest suites; app imports still resolve live. `test_new01_*` added. No sweep regressions required a fix.

## Retest

```
git fetch origin && git checkout cursor/evidence-expansion-coherence
git rev-parse HEAD   # descendant of e2a3216 (#39), 329e08b (#47), 18ef461 (#49)
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m unittest tests.test_new01_unittest_packaged_suite -v
# honesty greps
rg -n "e2_closed|run_integration_complete" docs/CANDIDATE_MANIFEST.md docs/SECURE_ENCLAVE_ADMISSION.md CHANGELOG.md
rg -n "com.darashkevich.runspecimen.holder" apps/holder/Resources/Info.plist apps/holder/Scripts/build_install_holder.sh
# hashes: sha256sum artifacts/rc15-2026-10-05-golden-master/runspecimen-0.2.0rc15* vs docs/CANDIDATE_MANIFEST.md
```

Prove NEW-01: a workspace `tests/__init__.py` + `tests/test_ok.py` through `UnittestProvider` must be `outcome=passed` / 1 test. Old runner at `6bb64d1` failed with `module incorrectly imported from …/tests`.

## Deliverable format

Honesty table (hardware / rc15 / E2 / holder id / hashes). Findings table `ID|Sev|Cat|Location|Evidence|Fix direction`. NEW-01 disposition. Residual debt ≤10 lines.

## Do not

Implement, merge, publish, retag, notarize, Store/PyPI/TestFlight, type APPROVE, press Touch ID/Face ID, or install the holder daemon.
