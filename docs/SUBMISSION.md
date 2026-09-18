# Marketplace and Registry Submission Guide

This document lists the manual actions required to publish RunSpecimen to
various distribution channels. Each section describes what must be done
by a human with appropriate credentials.

## Proposed release (not published yet)

Package / plugin identity on the release branch: **`0.2.0rc11`** / **`0.2.0-rc.11`**.

**Last published:** [v0.2.0-rc.10](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.10) / PyPI `runspecimen==0.2.0rc10`.

Prospective URLs (appear only after Yahor publishes the rc11 GitHub Release — that also triggers PyPI):

- Release URL: https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.11
- Wheel: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.11/runspecimen-0.2.0rc11-py3-none-any.whl
- Source: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.11/runspecimen-0.2.0rc11.tar.gz
- Plugin archive: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.11/runspecimen-plugin-0.2.0-rc.11.zip
- Checksums: https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.11/SHA256SUMS

## 1. Cursor Marketplace

**Status:** Not submitted

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
- [x] Logo committed and referenced: `assets/runspecimen-logo.png`
- [x] README.md documents usage
- [x] All paths are relative and valid
- [x] Plugin tested locally

**MANUAL ACTION REQUIRED:** Human must submit at https://cursor.com/marketplace/publish

---

## 2. Codex/ChatGPT Plugin Directory

**Status:** Not submitted

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
plugins/runspecimen/assets/runspecimen-logo.png  # 512 — Cursor plugin logo
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

**Status:** Package shipped in-repo; community marketplace **not submitted**

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

**Status:** Package shipped in-repo; gallery **not submitted**

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

**MANUAL ACTION REQUIRED:** Human must publish to the Gemini CLI extension
gallery when ready. Gemini Code Assist uses the same MCP script + project
instructions; there is no separate partner plugin SDK.

---

## 2e. JetBrains Junie / IntelliJ

**Status:** Junie catalog + IntelliJ scaffold in-repo; JetBrains Marketplace
**not submitted**

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

**Status:** Last published `0.2.0rc10`; **`0.2.0rc11` not published yet**

**Registry URL:** https://pypi.org/project/runspecimen/

### Proposed package (after Yahor publish approval)

- **Version:** `0.2.0rc11`
- **Install (after publish):** `python3 -m pip install runspecimen==0.2.0rc11`
- **Until then:** `python3 -m pip install runspecimen==0.2.0rc10`
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
verifies that the tag matches the package version, reruns the complete release
gate, transfers only the wheel and source distribution to a separate
OIDC-enabled job, and uploads them to PyPI. The GitHub `pypi` environment is
restricted to `v*` tags.

---

## 4. Website (runspecimen.darashkevich.com)

**Status:** Live (hexaflake mark + honest rc10 PyPI / git-main copy). Marketplace links stay pending until listings are accepted.

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
| GitHub Release | ❌ rc11 draft | publish click | last live: [v0.2.0-rc.10](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.10) | prospective [v0.2.0-rc.11](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.11) |
| Cursor Marketplace | ❌ | - | - | - |
| Codex Directory | ❌ | - | - | - |
| Claude Code community | ❌ | package ready in-repo | - | - |
| Grok Build | ❌ | Claude-compat package ready | - | local symlink / self-host |
| Gemini CLI gallery | ❌ | extension ready in-repo | - | - |
| JetBrains Junie / Marketplace | ❌ | Junie catalog + IntelliJ scaffold | - | - |
| Windsurf / Open VSX | ❌ | skill/rule pack ready | - | - |
| PyPI | ❌ (rc11) | after GitHub Release publish | last live: `0.2.0rc10` | [runspecimen](https://pypi.org/project/runspecimen/) |

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
6. **Junie:** `/extensions` shows `runspecimen` after marketplace add
7. **Windsurf:** `@runspecimen` skill resolves; rule appears under Customizations
8. **PyPI:** `pip install runspecimen` works and `runspecimen --version` shows `0.2.0rc11`
9. **Website:** Update with verified live links only
