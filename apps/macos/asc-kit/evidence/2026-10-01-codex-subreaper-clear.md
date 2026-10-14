# Linux subreaper leak after the 56ee890 recheck

Comment: https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5932238955

That comment was already implemented in `888b2c718ea492c26a8288eb70457f1d8ab882f8` (evidence tip `41cfcbd81605e7cc6326d1ee6b4529717310aa09`). PRs #40–#45 still have no comments newer than the rebase. This note records the Linux CI failure that implementation left behind, and the clear.

Code SHA: `e4c85cb33caa42208370e60d942a6f153e639105`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

Failed CI on `41cfcbd81605e7cc6326d1ee6b4529717310aa09`:

- https://github.com/darashkevich/runspecimen/actions/runs/36868829405
- https://github.com/darashkevich/runspecimen/actions/runs/36868836389

Every Ubuntu `release-check` job failed. `test_waitpid_on_an_orphan_is_not_an_exit_status` and `test_each_persistence_and_handshake_boundary` (`after_armed`) saw `waited` instead of `echild`. The holder had left `PR_SET_CHILD_SUBREAPER` set on the unittest process, so a later `waitpid` reaped a foreign orphan.

## Fix

The holder still sets the subreaper before the payload runs, records any reparented child while that subreaper is on, then clears it (`prctl` 36, 0) when the read loop ends and when spawn fails. A setsid grandchild that was already reparented still keeps the lease. A later orphan check is not the parent of that child.

Regression: `test_linux_subreaper_is_cleared_after_the_payload_exits`. It fails when the disable call is absent (`prctl` 36 stays 1) and passes when the last call is `prctl` 36, 0. Local suite `tests.test_execution_holder`, `tests.test_holder_protocol`, and `tests.test_launch_faults`: 81 tests, OK. Darwin cannot show the ECHILD failure; the regression records the `prctl` sequence.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 526 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-subreaper/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `a0264e70b02f34214c9e29a7e6c340078c8c81ad772a9dc8707663b6bc11f6f0` |
| sdist | `04770f9d07517113f12c67ae8bb9494b6eaa50cc279ae069c4e0f2e86ea333c3` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged. No Store package.

The GUI app sources did not change. The previous development GUI remains the build of `27bb0c7` app sources at `/tmp/rs-qa-codex-20261001/DerivedData/Build/Products/Release/RunSpecimen.app`. That bundle has no holder. This pass does not claim a new GUI acceptance.

This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. The live holder was not repaired. CI on this SHA is not claimed green here.
