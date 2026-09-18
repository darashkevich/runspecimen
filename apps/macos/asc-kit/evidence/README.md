# Local QA evidence (not App Store Connect uploads)

| File | What it proves |
| --- | --- |
| [mas-e2e-pty-last.json](mas-e2e-pty-last.json) | Sandboxed e2e on Apple Distribution archive: exact APPROVE prompt + still waiting; never typed APPROVE |
| [distribution-archive-last.txt](distribution-archive-last.txt) | Clean-checkout MAS archive: Apple Distribution app+helper, `--verify --strict`, export gate READY, `RS_MAS_EXPORT=0` |
| [export-mas-local-pkg-installer-profile-mismatch.txt](export-mas-local-pkg-installer-profile-mismatch.txt) | Local `destination=export` pkg failed: MAS profile does not include 3rd Party Mac Developer Installer (no upload) |
| [store-export-gate-last.txt](store-export-gate-last.txt) | Fail-closed profile gate + `codesign --verify --strict` unsigned/tamper negatives + Developer ID / ad-hoc / archive path binding |
| [export-mas-adhoc-archive-refused.txt](export-mas-adhoc-archive-refused.txt) | `export_mas` refuses ad-hoc archive before `xcodebuild -exportArchive` |
| [export-mas-mismatched-archive-app-bypass-refused.txt](export-mas-mismatched-archive-app-bypass-refused.txt) | Separate `RS_ARCHIVE_APP` cannot satisfy gate for a different `RS_ARCHIVE_PATH` |
| [export-mas-test-codesign-fixtures-refused.txt](export-mas-test-codesign-fixtures-refused.txt) | Production `export_mas` refuses `RS_TEST_CODESIGN_DV_*` fixtures |
| [export-mas-archive-real-codesign-adhoc.txt](export-mas-archive-real-codesign-adhoc.txt) | Real `codesign -dv` Authority/TeamIdentifier of archive binaries (not stubs) |

ASC product screenshots: see [`../screenshots/`](../screenshots/) (4 real ad-hoc MAS PNGs; not Connect Media uploads).
