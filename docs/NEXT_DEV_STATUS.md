# RunSpecimen next-dev status (post rc10)

**Date:** 2026-09-16  
**Baseline verified:** `v0.2.0-rc.10` @ `ceb18abc99797dee8b5cfbe26052809014338a89`  
**Hard stops:** no merge / PyPI republish / website deploy / marketplace submit without Yahor’s separate release decision.

## External blockers (read first)

| Blocker | Why it blocks | Owner |
| --- | --- | --- |
| **GitHub ↔ PyPI SHA-256 mismatch on rc10** | Release assets and PyPI wheel/sdist were produced by **separate rebuilds**. Digests do not match (see §Evidence). Integrity story is broken until the next RC uses a single validated build (or Yahor authorizes an exceptional republish). | Engineering (CI fix below); Yahor for any rc10 republish |
| **Apple Developer ID / notarization credentials** | Blocks shipping a signed/notarized macOS build as production. Unsigned builds must not be labeled production. | Yahor |
| **Cursor Marketplace submission** | Not submitted; acceptance is human + Cursor review. | Yahor |
| **Codex / OpenAI plugin submission** | Not submitted; listing requires portal + verified identity. | Yahor |
| **Real-user first-run study** | Dashboard/CLI IA exists on rc10; **no recorded external user-test evidence** yet — treat UX claims as author assumptions until tested. | Yahor / scheduled testers |

## Baseline (verified, not assumed)

| Surface | Status |
| --- | --- |
| GitHub tag / pre-release | Live: [v0.2.0-rc.10](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.10) |
| PyPI | Live: `runspecimen==0.2.0rc10` |
| Website | Live commit `99c5c9c` on darashkevich.com (`Publish RunSpecimen rc10 product site and brand assets`) |
| PR #7 (Ed25519 / rc10) | Merged |
| PR #5 (schema + dashboard IA) | **Superseded by #7 stack** — core schema/tests blobs match `main`; dashboard on `main` is a strict superset (a11y). Close without merging. |
| PR #6 (macOS app) | Open; remains separate |

### Evidence: rc10 digest split (do not republish unless asked)

| Artifact | GitHub Release SHA-256 | PyPI SHA-256 |
| --- | --- | --- |
| `runspecimen-0.2.0rc10-py3-none-any.whl` | `d82d04cc…6807e` | `26dd3aaf…f88d7` |
| `runspecimen-0.2.0rc10.tar.gz` | `086bd860…6f99f` | `369950aa…d3469` |
| `runspecimen-plugin-0.2.0-rc.10.zip` | `50b0f2a9…78d55` | (not on PyPI) |

Cause: `publish-pypi.yml` rebuilds on `release: published` for OIDC upload, while GitHub Release assets were attached from a different local/CI build.

## Priority plan (unblocked first)

1. **Release hygiene (CI)** — one validated build → GitHub Release assets + PyPI packages + SHA256SUMS + build provenance/attestation; keep OIDC trusted publishing. **Do not** retag/republish rc10 in this work.
2. **Brand / marketplace assets** — copy existing site brand pack into Cursor/Codex plugin paths; add Codex `interface.logo` / `composerIcon`; wire macOS `AppIcon*` into PR #6 only.
3. **Isolation** — ADR + narrow opt-in backend spike (capability discovery, fail-closed unmet policy, receipt-bound settings). No scheduler; no science-truth claims; do not equate timeout/path containment or macOS UI sandbox with payload isolation.
4. **First-run UX** — polish clean-install → verified receipt path; keep dashboard read-only / real-TTY approval. Label assumptions until user-test evidence exists.
5. **macOS** — boundary tests + signing/notarization checklist on PR #6; no unsigned “production” distribution.

## Marketplace status (actual)

| Channel | Actual status |
| --- | --- |
| Cursor Marketplace | **Not submitted** (repo docs + no live listing claimed) |
| Codex / OpenAI directory | **Not submitted** |
| PyPI | **Live** `0.2.0rc10` (digests ≠ GitHub assets — see blocker) |
| Website | **Live** rc10 product site; marketplace availability still correctly hedged |

## Deferred this session

- Republishing or retagging rc10
- Merging any PR
- Marketplace submit
- Full isolation backend beyond ADR + minimal spike
- Signed/notarized macOS shipping
- Claiming user-test completion without evidence

## Brand source of truth

Website pack: `sites/runspecimen/public/brand/` (see `brand/README.md` in the darashkevich.com repo). Engine/adapters must **copy** those assets — do not invent alternate marks.
