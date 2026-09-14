# Marketplace and Registry Submission Guide

This document lists the manual actions required to publish RunSpecimen to
various distribution channels. Each section describes what must be done
by a human with appropriate credentials.

## Current Release

- **Version:** 0.2.0-rc.9
- **Release URL:** https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.9
- **Wheel:** https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.9/runspecimen-0.2.0rc9-py3-none-any.whl
- **Source:** https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.9/runspecimen-0.2.0rc9.tar.gz
- **Plugin archive:** https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.9/runspecimen-plugin-0.2.0-rc.9.zip
- **Checksums:** https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.9/SHA256SUMS

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

### Submission steps (skills-only)

1. Open the OpenAI plugin submission portal
2. Select "Create plugin"
3. Choose "Skills only" submission type
4. Upload or point to the plugin package
5. Complete listing information
6. Wait for review

**MANUAL ACTION REQUIRED:** Human must submit via OpenAI Platform with verified identity

---

## 3. PyPI (Python Package Index)

**Status:** Not published

**Registry URL:** https://pypi.org/project/runspecimen/ (will exist after publication)

### Prerequisites

- PyPI account with publishing rights
- API token or trusted publisher configured
- `twine` installed

### Publication steps

```bash
# From clean checkout
pip install twine build

# Build distributions (already done in release)
python -m build

# Upload to PyPI
twine upload dist/runspecimen-0.2.0rc9*
```

### Using GitHub Actions (recommended)

Add `PYPI_API_TOKEN` secret to repository, then create a publish workflow
triggered on release creation.

**MANUAL ACTION REQUIRED:** Human must configure PyPI credentials and trigger upload

---

## 4. Website (runspecimen.darashkevich.com)

**Status:** Live but may need update

**Current content check:** Site mentions "Public marketplace availability is not yet confirmed."

### Update required

After marketplace submissions are accepted (not just submitted), update the
website to reflect actual public availability with direct links.

**Location:** Website is not in this repository. Hosted separately (Cloudflare).

**MANUAL ACTION REQUIRED:** Human must update website content after marketplace
listings are confirmed live (not pending review).

---

## Submission Status Tracking

| Channel | Submitted | Pending | Live | URL |
| --- | --- | --- | --- | --- |
| GitHub Release | ✅ | - | ✅ | [v0.2.0-rc.9](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.9) |
| Cursor Marketplace | ❌ | - | - | - |
| Codex Directory | ❌ | - | - | - |
| PyPI | ❌ | - | - | - |

**Important:** Do not claim a listing is "public" or "available" until:
1. Submission is accepted (not just submitted)
2. Listing is live and accessible to users
3. URL is verified working

---

## Verification after publication

After each channel goes live, verify:

1. **Cursor:** Search "runspecimen" in Cursor Marketplace
2. **Codex:** Search "runspecimen" in ChatGPT/Codex Plugins Directory
3. **PyPI:** `pip install runspecimen` works and `runspecimen --version` shows `0.2.0rc9`
4. **Website:** Update with verified live links only
