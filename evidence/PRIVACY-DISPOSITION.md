# Mac Release privacy decision — Yahor, 23 October 2026

Declared exactly: UserDefaults CA92.1; SystemBootTime 35F9.1 for monotonic elapsed-time/deadline measurements; FileTimestamp C617.1 and 3B52.1 for stat-family access in embedded Python, OpenSSL and frozen helper (container files and explicitly user-authorized workspace files).

DiskSpace is deliberately not declared. Embedded Python imports statvfs/fstatvfs, but these symbols are unused by RunSpecimen: no call sites in src/ or native Mac sources were found. This records the release owner's accepted unused-symbol disposition, not proof that no possible third-party path can invoke them. Per Yahor's decision, E174.1 will be added only if Apple asks; any future declaration must accurately describe actual approved use, rather than an invented low-space feature.

A symbol scan distinguishes imported capability from observed execution. Archive evidence lists every Mach-O file, hashes, imported symbols, manifest association and undeclared categories. Only DiskSpace imports are allowed by this documented exception; no ActiveKeyboards use was found. The exact-category gate rejects missing, extra, duplicate or wrong-reason entries. Shipping/Store acceptance, signing, upload and approval remain held. The rebuilt local unsigned Release archive is a candidate built from shipping sources, not an uploaded or distribution-signed Store artifact.


## Reproducible QA2 scan — 27 October 2026

The committed scanner is `apps/macos/Scripts/scan_required_reason_apis.py`. Run it with a built `.app` or `.xcarchive` path; it enumerates actual Mach-O files (including embedded libraries), hashes bytes, reads imported symbols with `xcrun nm -u`, associates the nearest bundled manifest and reports undeclared categories. Read/import errors fail rather than returning a clean empty scan. The separate exact-category manifest gate remains in place.

`evidence/QA2-current-mac-symbol-scan.json` was produced from the current local Release app with a freshly frozen CPython 3.12/PyInstaller 6.16.0 helper and explicit ad-hoc identity (`RS_SIGN_IDENTITY=-`). No provisioning, distribution identity, upload or trust change was used. Build: `RS_FREEZE_PYTHON=/tmp/qa2-build-venv/bin/python RS_SIGN_IDENTITY=- bash apps/macos/Scripts/build_app.sh --mas`; scan: `python3 apps/macos/Scripts/scan_required_reason_apis.py apps/macos/build/RunSpecimen.app`. The temporary interpreter path is illustrative; use an equivalent disposable environment with the recorded dependencies.

The scan again finds `_statvfs` and `_fstatvfs` imported by embedded Python. DiskSpace remains undeclared by the owner's standing decision. This is an unresolved Store-acceptance risk, not a scanner pass or evidence that the imports never execute. ActiveKeyboards was not found. No interpreter symbols were removed. Binary hashes and category results, rather than an uncommitted narrative, are retained in the JSON. Dynamic selectors and Apple catalog/reason applicability still require review; imported symbols alone cannot prove runtime use or Apple acceptance.
