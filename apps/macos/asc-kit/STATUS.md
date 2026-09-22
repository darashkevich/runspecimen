# ASC kit status (honest)

## Resubmitted 2026-09-21 (waiting for review)

Monday 02:08 CEST email: “There's an issue with your RunSpecimen (macos) submission”
for `cd198ca0` / **0.1.3 (6)**. Resolution Center text is still not in the public
ASC API. Same generic body as the first rejection.

| Connect field | Value |
| --- | --- |
| Version | **0.1.3** `WAITING_FOR_REVIEW` |
| App Info | `WAITING_FOR_REVIEW` |
| Build | **8** id `c5575ef9-2444-4452-aec8-c9afdc7dd611` `VALID` uploaded 2026-09-20T22:35:19-07:00 |
| Submission | `9c19e1cd-ebd1-4705-b683-5a5fdc2671f6` submitted 2026-09-21T05:36:49Z |
| Prior rejections | `5a2f17dd` (build 5) and `cd198ca0` (build 6) both `COMPLETE` after cancel |

Build 8 is the reviewer-demo tree plus: first-launch auto-open of Reviewer Demo,
Python CS entitlements on the app + inherit helper, no leftover `com.apple.python3`.
Engine **0.2.0rc12**. Not publicly available until Apple approves.

Account Holder still owns: Resolution Center reply if Apple writes back, and the
EU DSA trader declaration (Business → Compliance). The `/apps` banner is still up.

## Resubmitted 2026-09-19 (rejected overnight)

| Connect field | Value |
| --- | --- |
| Version | **0.1.3** `WAITING_FOR_REVIEW` |
| App Info | `WAITING_FOR_REVIEW` |
| Build | **6** id `643b57e5-c679-4dd3-a97b-8d64e23c29e6` `VALID` uploaded 2026-09-19T08:20:03-07:00 |
| Submission | `cd198ca0-c74c-4cbc-b626-89fd116030b9` submitted 2026-09-19T15:29:40Z |
| Prior rejection | cancelled (`5a2f17dd-…` COMPLETE) |

Build 6 is the reviewer-demo tree: bundled `Resources/ReviewerDemo`, no MAS pip/Select-CLI CTA, PyInstaller `Python3.framework` rewritten off `com.apple.python3`. Engine **0.2.0rc12**. Not publicly available until Apple approves.

## Prior rejection (2026-09-19 morning)

Apple rejected macOS **0.1.3 (5)** overnight. Emails at 02:13 CEST:
“There's an issue with your RunSpecimen (macOS) submission.” and
“Your App Review Feedback” (Changes needed). The public ASC API does **not**
return Resolution Center guideline text.

| Connect field | Value |
| --- | --- |
| Version | **0.1.3** `REJECTED` / `appVersionState=REJECTED` |
| App Info | **REJECTED** |
| Review submission | `5a2f17dd-3b82-4730-b0e5-ac1655845074` `UNRESOLVED_ISSUES` (actor APPLE) |
| Review item | version rejected; **no** review attachments |
| Draft submission | `cd198ca0-…` `READY_FOR_REVIEW` with **0** items (do not submit empty) |

What the rejected binary asked reviewers to do (build 5 / rc10):

- Empty-state **Select CLI** + footer `pip install runspecimen==0.2.0rc10`
- Review notes pointed at `examples/showcase` with **no zip attached**
- Showcase is not inside the Store `.app`

That is a 2.1 completeness / 2.4.5(ii)(viii) fail even without Apple’s paragraph.
Fix in this tree: bundled `Resources/ReviewerDemo`, MAS empty state **Open Reviewer Demo**,
no pip/Select-CLI on Store builds, metadata keywords no longer lead with “sandbox”.
That fix shipped as **0.1.3 (6)** (rejected) and again as **0.1.3 (8)**, which is the binary now in review. Engine **0.2.0rc12**.

Account Holder still owns: Resolution Center reply if Apple writes back, and the
EU DSA trader declaration (Business → Compliance). Do not cancel the build 8 submission.

App Store Connect queried **2026-09-18** via the App Store Connect API
(`GET /v1/apps?filter[bundleId]=com.darashkevich.runspecimen` and included
version/build/submission resources). Credentials are local-only; this file
records public Connect identifiers, not secrets.

## Historical: Connect build 5 (2026-09-18)

This section records what Apple had when build 5 was in review. It is **not** the current binary. The submission now in review is **0.1.3 (8)** — see the top of this file.
The ASC API does **not** store a git SHA. Identity below is reconstructed from
Connect timestamps + the git timeline.

| Connect field | Value |
| --- | --- |
| App | `6813492506` `RunSpecimen` `com.darashkevich.runspecimen` SKU `runspecimen-mac` |
| macOS version | **0.1.3** id `6cfe298b-92c1-460d-b83b-5687a67f2cff` `MAC_OS` `releaseType=AFTER_APPROVAL` |
| State | was `WAITING_FOR_REVIEW`, later rejected (not the current submission) |
| Submission | `appStoreVersionSubmissions` id `6cfe298b-92c1-460d-b83b-5687a67f2cff` |
| Build | **5** id `17c7d179-78e4-4b93-86ce-753cef186b20` `processingState=VALID` `expired=false` min OS 14.0 |
| Uploaded | `2026-09-18T06:38:17-07:00` (**15:38 CEST**) |
| pkg (Connect) | `0158194a-cc9c-419e-ae26-c6fb9be0e636.pkg` |
| Icon (Connect media) | 1024 App Store token, `hasPrerenderedIcon: true` (media ≠ compiled `Assets.car`) |

**Closest committed source:** `eba1abe` (PR #6 merge, 13:32 CEST) — the last
`main` commit **before** the upload. That tree is engine **`0.2.0rc10`**,
`CFBundleVersion` **4**, AppIcon via `Resources/AppIcon.icns` (no
`Assets.xcassets` catalog). Connect reports build **5**; git still said **4**.
Likely Xcode `manageAppVersionAndBuildNumber` (or an uncommitted local bump)
assigned 5 at export/upload. **Not** `ecc1709` / PR #15.

Commits that **cannot** be inside Apple’s binary (all after 15:38 CEST):

| Time (CEST) | Commit | Why it matters |
| --- | --- | --- |
| 16:15 | `2fe30c1` / `5234f7f` | Asset catalog (email-style filenames `icon_*@2x.png` / `*@email`) + git build **5** |
| 16:43 | `4f907c4` | Hexaflake mark across plugins + native AppIcon |
| 16:56 | `a4c007e` | Engine identity **0.2.0rc11** |
| 18:19 | `9fe2312` | Catalog filenames fixed; 128@2x is 256px; store-export `--verify --strict` |
| 18:30 | `ab2e07c` | Undersized on-screen windows sanitize to `minSize` |

### User-visible / safety-relevant diffs vs PR #15

| Surface | Build 5 (Apple) | PR #15 / this branch |
| --- | --- | --- |
| Frozen engine | **0.2.0rc10** (rc11 identity did not exist yet) | **0.2.0rc12** identity; freeze must match `__version__` |
| Incident bundle / remote-confirm refuse / `confirm_channel` | absent | present in engine |
| AppIcon in `.app` | icns from PR #6; no compiled catalog | hexaflake `Assets.car` + `icon_*@2x.png` with matching pixels |
| Window placement | no later clamp / `minSize` sanitize | tiny on-screen frames grow to minimum |
| Store export gate | not in the runtime binary | `--verify --strict` + tamper negatives (packaging) |
| Connect 1024 icon | present as media | still a separate Connect asset |

### Recommendation (superseded)

Build **8** is already `WAITING_FOR_REVIEW` (submitted 2026-09-21). Do not cancel it and do not attach another build from automation. The paragraphs above describe why build 5 was the wrong binary to leave in review.

## Packaging checklist (this operator Mac)

| Item | Status |
| --- | --- |
| Ad-hoc Archive + nested helper sandbox+inherit | Done (local) |
| Engine freeze | Build **8** ships engine **0.2.0rc12** |
| PrivacyInfo + AppIcon | Done — catalog filenames are `icon_*@2x.png` with matching pixel sizes |
| Positive sandboxed e2e | Done via `Scripts/test_mas_sandbox_e2e.sh` — requires **actual** `Type 'APPROVE' to bind…` prompt + session still waiting; never types APPROVE |
| Store export fail-closed | Done — `codesign --verify --strict` on archived app + nested helper (tamper-after-signing refused) |
| Metadata / reviewer demo copy | Ready in this kit |
| ASC screenshot PNGs | **Captured** — 4 real app PNGs under [screenshots/](screenshots/) |
| Local e2e / gate evidence | [evidence/](evidence/) |
| Apple Distribution cert + MAS profile | **Present** (2026-09-18): `Apple Distribution: YAHOR DARASHKEVICH (UN6KF8636A)`; installer `3rd Party Mac Developer Installer: YAHOR DARASHKEVICH (UN6KF8636A)` in the keychain; profile `RunSpecimen MAS` UUID `0c5ef3dc-ebad-429b-8928-fdfcfee98c29` (`OSX`, `UN6KF8636A.com.darashkevich.runspecimen`, **one** Application `DeveloperCertificate`, no `get-task-allow`, no `ProvisionedDevices`). The profile **correctly omits** the installer cert (code-signing EKU vs installer EKU). Do **not** regenerate the app profile “to include” the installer identity. Developer ID Application is **not** a MAS substitute. |
| Distribution-signed archive | **Done** — `RS_MAS_EXPORT=0 ./Scripts/archive_mas.sh` from `/tmp/rs-clean-checkout` (`44ddfed`). App + helper `TeamIdentifier=UN6KF8636A`, Authority `Apple Distribution`, `codesign --verify --strict`, App Sandbox + helper inherit, `Assets.car` + `AppIcon.icns`. |
| Local MAS `.pkg` export | **Done** — `RS_EXPORT_DESTINATION=export` + `installerSigningCertificate` + profile **UUID** (display name `RunSpecimen MAS` is not what `exportArchive` resolves). Proof: [evidence/export-mas-local-pkg-ok.txt](evidence/export-mas-local-pkg-ok.txt). SHA-256 `e6ea0a7f12f4094ed430ea1ebc956ad6db2d67ecfa0f52e1eb0ebb66283f1bbf`. Extracted app **0.1.3 (5)** `mas`, both binaries `--verify --strict`, sandbox + inherit. **This local pkg is not what Apple is reviewing** (exported after PR #15 packaging fixes). First attempt without installer cert / UUID: [evidence/export-mas-local-pkg-installer-profile-mismatch.txt](evidence/export-mas-local-pkg-installer-profile-mismatch.txt). |
| `ExportOptions.mas.plist` committed `teamID` | Still placeholder `TEAMID`; `export_mas.sh` rewrites a temp copy (team ID + profile UUID). Default `destination=upload` — set `RS_EXPORT_DESTINATION=export` for a local pkg. Never `-allowProvisioningUpdates` without Yahor. |
| Connect upload | **0.1.3 (8)** `WAITING_FOR_REVIEW` since 2026-09-21. Do not upload a replacement while it is waiting. |

State ladder (do not collapse these):

1. **Uploaded** — build 8 is in Connect (`c5575ef9-2444-4452-aec8-c9afdc7dd611`).
2. **Processing** — finished; `VALID`.
3. **Waiting for review** — current state (submission `9c19e1cd-…`, 2026-09-21).
4. **Approved** — not yet.
5. **Publicly available** — not yet (`AFTER_APPROVAL` will still need Apple to release it).

Do not merge/publish/submit from automation without Yahor’s release decision.
Do not treat WAITING_FOR_REVIEW as a live Mac App Store install.
