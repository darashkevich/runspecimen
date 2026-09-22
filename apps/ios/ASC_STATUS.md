# RunSpecimen Observe — ASC / TestFlight status

Queried **2026-09-22** via App Store Connect API (local AuthKey; no secrets in this file).

## Ready locally

- Bundle ID registered: `com.darashkevich.runspecimen.observe` (Developer portal id `83TS8H28M7`)
- App Store provisioning profile **ACTIVE**: `RunSpecimen Observe App Store` (`YPLN4MZQ77` / UUID `2b4df713-ec58-4135-bf50-d16df1b48b61`)
- IPA built: `apps/ios/build/ipa/RunSpecimenObserve.ipa` (version **0.1.0** / build **1**, not committed)
- Archive signed with Apple Distribution team `UN6KF8636A`

## Blocked on Yahor (portal / legal)

1. **Create ASC app** for bundle `com.darashkevich.runspecimen.observe`  
   My App Store Connect API key can GET/UPDATE apps but **cannot CREATE** (`FORBIDDEN_ERROR` on `POST /v1/apps`).  
   Portal: App Store Connect → My Apps → **+** → iOS → name **RunSpecimen Observe**, SKU `runspecimen-observe-ios`, bundle id above.  
   After create, re-run:  
   `xcrun altool --upload-app -f apps/ios/build/ipa/RunSpecimenObserve.ipa -t ios --apiKey <KEY_ID> --apiIssuer <ISSUER>`
2. **EU DSA trader declaration** (Account Holder): Business → Compliance. Banner still affects the account; not completable via this API key.
3. **TestFlight / App Store listing** (screenshots, privacy, review notes) after the first build processes — do not claim submitted until upload succeeds.

## Leave alone

- Mac App Store `com.darashkevich.runspecimen` **0.1.3 (8)** remains `WAITING_FOR_REVIEW` (submission `9c19e1cd-ebd1-4705-b683-5a5fdc2671f6`). Do not cancel/resubmit while waiting.

## Safety

Observe keeps `can_approve` false. No agent auto-approve. TTY APPROVE on Mac remains primary.
