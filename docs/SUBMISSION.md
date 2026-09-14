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

- A PyPI account with two-factor authentication enabled
- A pending Trusted Publisher for the `runspecimen` project

### Trusted Publisher configuration

The repository includes `.github/workflows/publish-pypi.yml`. It uses GitHub
OIDC and does not require a stored PyPI API token. Register a pending publisher
at https://pypi.org/manage/account/publishing/ with these exact values:

| Field | Value |
|---|---|
| PyPI project name | `runspecimen` |
| GitHub owner | `darashkevich` |
| GitHub repository | `runspecimen` |
| Workflow filename | `publish-pypi.yml` |
| Environment name | `pypi` |

A pending publisher creates the project during the first successful publish;
it does not reserve the project name before then. Enter every identity field
exactly as shown.

### Publication steps

1. Register the pending publisher in PyPI.
2. Open the repository's **Publish Python package to PyPI** workflow.
3. Choose **Run workflow**, enter `v0.2.0-rc.9`, and run it from the default
   branch.
4. Confirm that https://pypi.org/project/runspecimen/ exists and that
   `python3 -m pip install runspecimen==0.2.0rc9` succeeds in a clean
   environment.

The workflow checks out the immutable tag, verifies that it matches the
package version, reruns the complete release gate, transfers only the wheel
and source distribution to a separate OIDC-enabled publish job, and then
uploads them to PyPI.

**MANUAL ACTION REQUIRED:** Sign in to PyPI and register the pending Trusted
Publisher. No token should be created or stored in GitHub.

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
