# Local QA evidence (not App Store Connect uploads)

| File | What it proves |
| --- | --- |
| [mas-e2e-pty-last.json](mas-e2e-pty-last.json) | Sandboxed e2e: exact APPROVE prompt + still waiting; never typed APPROVE (latest: engine **0.2.0rc12**) |
| [qa-rc12-local.txt](qa-rc12-local.txt) | Local release_check + Mac smoke + iOS build + artifact SHA-256 (not a published tag) |
| [distribution-archive-last.txt](distribution-archive-last.txt) | Clean-checkout MAS archive: Apple Distribution app+helper, `--verify --strict`, export gate READY, `RS_MAS_EXPORT=0` |
| [export-mas-local-pkg-installer-profile-mismatch.txt](export-mas-local-pkg-installer-profile-mismatch.txt) | First local `destination=export` failure: ExportOptions named the installer cert only as `signingCertificate` and used profile **display name** |
| [export-mas-local-pkg-ok.txt](export-mas-local-pkg-ok.txt) | Local Store pkg succeeded: `installerSigningCertificate` + profile UUID `0c5ef3dc-ebad-429b-8928-fdfcfee98c29`; installer chain + `--verify --strict` |
| [store-export-gate-last.txt](store-export-gate-last.txt) | Fail-closed profile gate + `codesign --verify --strict` unsigned/tamper negatives + Developer ID / ad-hoc / archive path binding |
| [export-mas-adhoc-archive-refused.txt](export-mas-adhoc-archive-refused.txt) | `export_mas` refuses ad-hoc archive before `xcodebuild -exportArchive` |
| [export-mas-mismatched-archive-app-bypass-refused.txt](export-mas-mismatched-archive-app-bypass-refused.txt) | Separate `RS_ARCHIVE_APP` cannot satisfy gate for a different `RS_ARCHIVE_PATH` |
| [export-mas-test-codesign-fixtures-refused.txt](export-mas-test-codesign-fixtures-refused.txt) | Production `export_mas` refuses `RS_TEST_CODESIGN_DV_*` fixtures |
| [export-mas-archive-real-codesign-adhoc.txt](export-mas-archive-real-codesign-adhoc.txt) | Real `codesign -dv` Authority/TeamIdentifier of archive binaries (not stubs) |

ASC product screenshots: see [`../screenshots/`](../screenshots/) (4 real ad-hoc MAS PNGs; not Connect Media uploads).
