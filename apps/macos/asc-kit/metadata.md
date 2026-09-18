# ASC metadata (paste into App Store Connect)

**Status:** copy is ready; ASC app record / localization fields in Connect are **pending** Yahor.

| Field | Value | Status |
| --- | --- | --- |
| Bundle ID | `com.darashkevich.runspecimen` | Fixed in Xcode / Info |
| SKU | `runspecimen-macos` (suggestion) | **Pending** — set in Connect |
| Name | RunSpecimen | Ready |
| Subtitle (≤30) | Local evidence control surface | Ready |
| Category | Developer Tools | Ready |
| Content rights | Does not use third-party content | Ready (confirm) |
| Age rating | 4+ / none of the above | **Pending** questionnaire in Connect |
| Pricing | Free (suggestion) | **Pending** Yahor |
| Availability | All territories (suggestion) | **Pending** Yahor |

## Promotional text (optional, ≤170)

Local safety and evidence control for one human-approved bounded run. Sandboxed SwiftUI shell; enforcement is the bundled CLI. No telemetry.

## Description

RunSpecimen is a local control surface for exactly one human-approved, bounded run at a time.

The Mac app is a sandboxed SwiftUI shell. Enforcement lives in the bundled `runspecimen` engine (frozen Mach-O helper — no host Python required). Approval requires an interactive PTY: you type APPROVE yourself. The app never auto-approves and exposes no agent API.

What you get:

- Native status, evidence, and certificate inspection
- Interactive Approve sheet on a real TTY
- Optional loopback-only, read-only dashboard (cannot approve or execute)
- Security-scoped workspace bookmarks for App Sandbox

Honest limits: App Sandbox confines the UI and its inherit helper. It does **not** OS-sandbox the payload under test. Certificates are hash-chained receipts, not asymmetric digital signatures. No telemetry.

Support: https://runspecimen.darashkevich.com/support/
Privacy: https://runspecimen.darashkevich.com/privacy/

## Keywords (≤100 chars, comma-separated)

runspecimen,evidence,approval,local,cli,sandbox,developer,receipt,preflight

## URLs

| URL type | Value | Status |
| --- | --- | --- |
| Support | https://runspecimen.darashkevich.com/support/ | Ready (verify live) |
| Privacy Policy | https://runspecimen.darashkevich.com/privacy/ | Ready (verify live) |
| Marketing | https://runspecimen.darashkevich.com/ | Ready |

## Version info

| Key | Value |
| --- | --- |
| Short version | 0.1.3 |
| Build | 4 |
| Bundled engine | 0.2.0rc10 |
| Min macOS | 14.0 |

## App Privacy

Declare **Data Not Collected** while true (no analytics, crash uploaders, ads, accounts, phone-home). Align with `Resources/PrivacyInfo.xcprivacy` (`NSPrivacyTracking=false`, empty collected types, UserDefaults `CA92.1` for bookmarks).

## Export compliance

Uses HTTPS only for optional docs links in-browser. Standard export-compliance answers apply — **pending** confirmation in Connect.

## Copyright

Copyright © RunSpecimen Contributors. Apache-2.0.
