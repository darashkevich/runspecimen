# Marketplace and Registry Submission Guide

This document lists the manual actions required to publish RunSpecimen to
various distribution channels. Each section describes what must be done
by a human with appropriate credentials.

## Published release

Package / plugin identity: **`0.2.0rc14`** / **`0.2.0-rc.14`**.

**Published:** [v0.2.0-rc.14](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.14) / PyPI `runspecimen==0.2.0rc14`. GitHub Release assets and PyPI are the same bytes (checksum-only; not SLSA-attested).

**Do not publish** the existing draft [v0.2.0-rc.11](https://github.com/darashkevich/runspecimen/releases/tag/untagged-784a2101f44640f11122) (annotated tag peels to `ecc1709`). Do not move that tag. Do not move `v0.2.0-rc.12`. See [RELEASE_IDENTITY.md](RELEASE_IDENTITY.md).

Published URLs:

- Release URL: https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.14
- Wheel: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.14/runspecimen-0.2.0rc14-py3-none-any.whl
- Source: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.14/runspecimen-0.2.0rc14.tar.gz
- Plugin archive: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.14/runspecimen-plugin-0.2.0-rc.14.zip
- Checksums: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.14/SHA256SUMS

## 1. Cursor Marketplace

**Status (2026-09-21):** Publish form submitted (“Thanks for applying”). **Not listed.** In-repo
`.cursor-plugin/marketplace.json` is packaging, not an approved public listing.

**Submission URL:** https://cursor.com/marketplace/publish

**Alternative:** https://cursor.directory (community-focused portal)

### Prerequisites

- Public Git repository with valid plugin manifest
- Logo committed to repo (optional but recommended)
- README.md documenting usage

### Submission steps

1. Go to https://cursor.com/marketplace/publish
2. Submit repository URL: `https://github.com/darashkevich/runspecimen`
3. Plugin path within repo: `plugins/runspecimen`
4. Wait for manual review (typically 1-2 weeks)

### Plugin manifest location

```
plugins/runspecimen/.cursor-plugin/plugin.json
```

### Review checklist (from Cursor docs)

- [x] Plugin has valid `.cursor-plugin/plugin.json` manifest
- [x] `name` is unique, lowercase, kebab-case: `runspecimen`
- [x] `description` clearly explains purpose
- [x] Logo committed and referenced: `assets/logo.png`
- [x] README.md documents usage
- [x] All paths are relative and valid
- [x] Plugin tested locally

Form submitted 2026-09-21. Do not claim a public Cursor Marketplace listing until Anysphere accepts it.

---

## 2. Codex/ChatGPT Plugin Directory

**Status (2026-09-21):** **Not submitted** and **not listed**. OpenAI still requires a verified developer identity (Persona camera ID) before the skills-only zip can be uploaded. Do not treat in-repo Codex plugin files as an approved directory listing.

**Submission URL:** OpenAI plugin submission portal (https://platform.openai.com)

### Prerequisites for skills-only submission

- Valid `.codex-plugin/plugin.json` manifest
- Skills defined in `skills/` directory

### Prerequisites for MCP-backed submission (if applicable)

- Production HTTPS MCP server URL
- Domain verification challenge completed
- Website, support, privacy policy, and terms URLs (HTTPS, max 1024 chars)
- Demo recording URL showing main use cases
- Exactly 5 positive and 3 negative test cases
- Release notes
- Verified identity in OpenAI Platform Dashboard

### Plugin manifest location

```
plugins/runspecimen/.codex-plugin/plugin.json
```

Copy-out logos (hexaflake, square RGB):

```
plugins/runspecimen/assets/logo.png              # 512 — interface.logo
plugins/runspecimen/assets/composer-icon.png     # 128 — interface.composerIcon
plugins/runspecimen/assets/logo.png  # 512 — Cursor plugin logo
```

### Submission steps (skills-only)

1. Open the OpenAI plugin submission portal
2. Select "Create plugin"
3. Choose "Skills only" submission type
4. Upload or point to the plugin package
5. Complete listing information
6. Wait for review

**MANUAL ACTION REQUIRED:** Human must submit via OpenAI Platform with verified identity

---

## 2b. Claude Code marketplace

**Status (2026-09-21):** Directory form **submitted for review** at https://platform.claude.com/plugins/submit. **Not listed** until Anthropic accepts it.

**References:**
- Plugin reference: https://code.claude.com/docs/en/plugins-reference
- Marketplaces: https://code.claude.com/docs/en/plugin-marketplaces
- Community catalog: `anthropics/claude-plugins-community` (public submission path)
- Official curated catalog is invite/discretion-only (not an application guarantee)

### Package locations

```
plugins/runspecimen/.claude-plugin/plugin.json
.claude-plugin/marketplace.json
plugins/runspecimen/.mcp.json
plugins/runspecimen/hooks/claude-hooks.json   # PreToolUse only (Claude schema)
```

### Local install (before marketplace acceptance)

```bash
# From a clone of this repo:
claude plugin marketplace add ./
claude plugin install runspecimen@runspecimen
# or symlink plugins/runspecimen into a Claude plugins/skills directory
```

**MANUAL ACTION REQUIRED:** Human must submit to the Claude community marketplace
when ready. Do not claim official Anthropic marketplace listing without acceptance.

---

## 2c. Grok Build (xAI)

**Status:** Shipped via Claude Code compatibility + `plugins/runspecimen/grok/`

Grok Build discovers Claude plugins/skills/hooks/MCP. Install:

```bash
mkdir -p ~/.grok/plugins
ln -sfn "$(pwd)/plugins/runspecimen" ~/.grok/plugins/runspecimen
grok plugin validate ~/.grok/plugins/runspecimen
```

See `plugins/runspecimen/grok/README.md`. No separate xAI partner plugin SDK is
required today; treat any Grok marketplace listing as **not submitted** until
published intentionally.

**MANUAL ACTION REQUIRED:** Optional self-hosted marketplace source when Yahor
wants in-product discovery beyond the symlink path.

---

## 2d. Gemini CLI extension gallery

**Status (2026-09-21):** GitHub topic `gemini-cli-extension` and repo-root `gemini-extension.json` are on `main` (`68c334d`). The gallery crawler runs daily. **Not indexed yet.**

**References:**
- Extensions: https://geminicli.com/docs/extensions/
- Extension reference: https://geminicli.com/docs/extensions/reference/
- Hooks: https://geminicli.com/docs/hooks/reference/

### Package locations

```
plugins/runspecimen/gemini-extension.json
plugins/runspecimen/GEMINI.md
plugins/runspecimen/commands/*.toml
plugins/runspecimen/hooks/hooks.json   # BeforeTool only (Gemini; Claude uses claude-hooks.json)
plugins/runspecimen/gemini/README.md
```

### Local install

```bash
gemini extensions link "$(pwd)/plugins/runspecimen"
# or: gemini extensions install "$(pwd)/plugins/runspecimen"
```

Gallery indexing is the crawler, not a form. Gemini Code Assist uses the same MCP script + project
instructions; there is no separate partner plugin SDK. Do not claim a gallery listing until it appears.

---

## 2d-bis. Antigravity CLI (`agy`)

**Status:** Native plugin shipped in-repo under `plugins/runspecimen/antigravity/`.
Gallery / marketplace **not submitted**. Dual path with enterprise Gemini CLI
(parent extension + `BeforeTool`) is documented; do not claim a gallery listing.

**References:**
- Migration: https://www.antigravity.google/docs/cli/gcli-migration
- Plugins: https://www.antigravity.google/docs/plugins
- Skills: https://www.antigravity.google/docs/skills/
- MCP: https://antigravity.google/docs/mcp/
- Hooks: https://antigravity.google/docs/hooks/

### Package locations

```
plugins/runspecimen/antigravity/plugin.json
plugins/runspecimen/antigravity/mcp_config.json
plugins/runspecimen/antigravity/hooks.json      # PreToolUse (Antigravity schema)
plugins/runspecimen/antigravity/skills/
plugins/runspecimen/antigravity/rules/
plugins/runspecimen/antigravity/scripts/        # copies of shared gate + MCP
plugins/runspecimen/antigravity/README.md
```

### Local install

```bash
agy plugin install "$(pwd)/plugins/runspecimen/antigravity"
# or: agy plugin import gemini  (after linking the parent Gemini extension;
#     then replace hooks with antigravity/hooks.json — BeforeTool ≠ PreToolUse)
```

**MANUAL ACTION REQUIRED:** Any Antigravity gallery / curated listing is
human-only when Yahor wants it. Do not claim listing.

---

## 2d-ter. Meta Muse Code

**Status:** Skill + MCP fragment shipped; PreToolUse gate example marked
**beta**. Marketplace **not submitted**.

**References:**
- Extending: https://dev.meta.ai/docs/muse-code/extending/

### Package locations

```
plugins/runspecimen/muse/README.md
plugins/runspecimen/muse/skills/runspecimen/SKILL.md
plugins/runspecimen/muse/examples/mcp_settings.fragment.json
plugins/runspecimen/muse/examples/hooks.beta.json
```

### Local install

```bash
muse skills install "$(pwd)/plugins/runspecimen/muse/skills/runspecimen" --scope project
# Merge examples/mcp_settings.fragment.json into Muse settings (absolute MCP path).
# Optional beta: copy examples/hooks.beta.json → .muse/hooks.json (edit ABS paths).
```

Do **not** document Muse `--yolo` / `--disable-approval` as RunSpecimen-compatible.
Cloud / remote threads cannot settle local TTY `APPROVE`.

**MANUAL ACTION REQUIRED:** Muse marketplace submission is human-only; not done.

---

## 2e. JetBrains Junie / IntelliJ

**Status (2026-09-21):** Catalog PR https://github.com/JetBrains/junie-extensions/pull/16 is open. **Not merged** and not a Marketplace listing.

### Package locations

```
.junie-extension/marketplace.json
plugins/runspecimen/extension.json
plugins/runspecimen/jetbrains/
plugins/runspecimen/mcp/.mcp.json
plugins/runspecimen/guidelines/runspecimen.md
```

### Local install (Junie)

```text
/extensions → Marketplaces → Add → /absolute/path/to/runspecimen
→ Install runspecimen
```

IntelliJ scaffold: see `plugins/runspecimen/jetbrains/intellij-plugin/README.md`
(Tools menu only; no Approve action).

**MANUAL ACTION REQUIRED:** Official JetBrains curated Junie catalog and
IntelliJ Marketplace submissions are human-only when Yahor wants them.

---

## 2f. Windsurf (Cascade)

**Status:** Skill/rule pack shipped; VS Marketplace / Open VSX **not submitted**

### Package locations

```
plugins/runspecimen/windsurf/README.md
plugins/runspecimen/windsurf/skills/runspecimen/SKILL.md
plugins/runspecimen/windsurf/rules/runspecimen.md
```

### Local install

```bash
mkdir -p .windsurf/skills .windsurf/rules
ln -sfn "$(pwd)/plugins/runspecimen/windsurf/skills/runspecimen" .windsurf/skills/runspecimen
ln -sfn "$(pwd)/plugins/runspecimen/windsurf/rules/runspecimen.md" .windsurf/rules/runspecimen.md
```

**MANUAL ACTION REQUIRED:** Optional dedicated UI extension / marketplace
listing later; filesystem skills/rules are the supported path today.

---

## 3. PyPI (Python Package Index)

**Status:** **`0.2.0rc14` is the published package** (identical bytes to the GitHub Release). **`0.2.0rc12` stays as the previous release.** **`0.2.0rc11` draft must stay unpublished.**

**Registry URL:** https://pypi.org/project/runspecimen/0.2.0rc14/

### Published package

- **Version:** `0.2.0rc14`
- **Install:** `python3 -m pip install runspecimen==0.2.0rc14`
- **Publishing:** GitHub Actions trusted publishing with OIDC; no PyPI API
  token is stored in GitHub.

### Trusted Publisher configuration

The active PyPI trusted publisher has these values:

| Field | Value |
|---|---|
| PyPI project name | `runspecimen` |
| GitHub owner | `darashkevich` |
| GitHub repository | `runspecimen` |
| Workflow filename | `publish-pypi.yml` |
| Environment name | `pypi` |

The repository's `.github/workflows/publish-pypi.yml` runs automatically when
a GitHub release is published. It checks out the immutable release tag,
verifies that the tag matches the package version, **downloads the GitHub
Release assets** (wheel, sdist, plugin zip, SHA256SUMS), verifies SHA-256
digests and filenames, and uploads **those same wheel/sdist bytes** to PyPI.
It does **not** rebuild distributions at publish time.

**rc12 provenance:** checksum-only. `SHA256SUMS` is the integrity contract.
`gh attestation verify` is expected to 404 until a future CI-built release
attaches SLSA / GitHub Artifact Attestation provenance. Do not describe this
candidate as attested.

The GitHub `pypi` environment is restricted to `v*` tags.

Public product/support/privacy/terms pages pin **rc12**. Do not retarget download links
from a draft. Do not publish the rc11 draft.

---

## 3b. Mac App Store (`com.darashkevich.runspecimen`)

**Status (App Store Connect, 2026-09-21):** macOS version **0.1.3 (8)** and
App Info are **WAITING_FOR_REVIEW** (submission `9c19e1cd-ebd1-4705-b683-5a5fdc2671f6`, submitted 2026-09-21T05:36:49Z). Builds 5 and 6 were rejected. Not publicly available. Do not upload another build while this submission is waiting.

Do **not** add a MAS link to the marketing site until Apple provides a live
`apps.apple.com` URL. Developer ID notarization is not a Store submission.

Details: `apps/macos/asc-kit/STATUS.md`.

---

## 4. Website (runspecimen.darashkevich.com)

**Status:** Live (hexaflake mark + `runspecimen==0.2.0rc14`). Marketplace links stay pending until listings are accepted.

**Current content check:** Site mentions "Public marketplace availability is not yet confirmed."

### Update required

After marketplace submissions are accepted (not just submitted), update the
website to reflect actual public availability with direct links.

**Location:** Marketing site lives in the `darashkevich.com` repo (`sites/runspecimen/`).

**MANUAL ACTION REQUIRED:** Human must update website content after marketplace
listings are confirmed live (not pending review).

---

## Submission Status Tracking

| Channel | Submitted | Pending | Live | URL |
| --- | --- | --- | --- | --- |
| GitHub Release | ✅ published prerelease | — | [v0.2.0-rc.14](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.14) | keep draft [v0.2.0-rc.11](https://github.com/darashkevich/runspecimen/releases/tag/untagged-784a2101f44640f11122) unpublished; do not move `v0.2.0-rc.12` |
| Cursor Marketplace | form submitted 2026-09-21 | Anysphere review | no public listing yet | https://cursor.com/marketplace/publish |
| Codex Directory | ❌ | not submitted (Persona identity still required) | no public listing | https://chatgpt.com/apps |
| Claude Code community | submitted 2026-09-21 | Anthropic review | not listed yet | https://platform.claude.com/plugins/submit |
| Grok Build | ❌ | Claude-compat package ready | - | local symlink / self-host |
| Gemini CLI gallery | topic + root manifest on `main` (`68c334d`) | daily crawler | not indexed yet | repo-root `gemini-extension.json` |
| Antigravity CLI (`agy`) | ❌ | native plugin ready | not submitted | local `agy plugin install` / import path |
| Meta Muse Code | ❌ | skill + MCP + beta hooks | not submitted | local skill/MCP install |
| JetBrains Junie / Marketplace | PR open | JetBrains review | not merged | https://github.com/JetBrains/junie-extensions/pull/16 |
| Windsurf / Open VSX | ❌ | skill/rule pack ready | - | - |
| PyPI | ✅ | — | `0.2.0rc14` (same bytes as GitHub) | [runspecimen 0.2.0rc14](https://pypi.org/project/runspecimen/0.2.0rc14/) |
| Homebrew tap | ✅ | — | `0.2.0rc14` sdist from GitHub Release | [darashkevich/homebrew-runspecimen](https://github.com/darashkevich/homebrew-runspecimen) |
| Mac App Store | ⏳ WAITING_FOR_REVIEW | Apple review of macOS **0.1.3 (8)** | not public | no `apps.apple.com` URL — see `apps/macos/asc-kit/STATUS.md` |

**Important:** Do not claim a listing is "public" or "available" until:
1. Submission is accepted (not just submitted)
2. Listing is live and accessible to users
3. URL is verified working

---

## Verification after publication

After each channel goes live, verify:

1. **Cursor:** Search "runspecimen" in Cursor Marketplace
2. **Codex:** Search "runspecimen" in ChatGPT/Codex Plugins Directory
3. **Claude Code:** `/plugin` discover after marketplace add; confirm skill + MCP
4. **Grok Build:** `grok inspect` shows skill/hooks/MCP after symlink
5. **Gemini CLI:** `/extensions list` after link/install; confirm MCP + hooks
6. **Antigravity (`agy`):** `agy plugin list` + `/hooks` + `/mcp` after install
7. **Muse Code:** `muse skills list` shows runspecimen; MCP optional; hooks beta
8. **Junie:** `/extensions` shows `runspecimen` after marketplace add
9. **Windsurf:** `@runspecimen` skill resolves; rule appears under Customizations
10. **PyPI:** `pip install runspecimen==0.2.0rc14` works and `runspecimen --version` shows `0.2.0rc14`
11. **Homebrew:** `brew install darashkevich/runspecimen/runspecimen` installs `0.2.0rc14` from the published sdist
12. **Website:** Update with verified live links only
