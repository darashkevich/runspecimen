# iOS Observe — local QA evidence

Files here are **local QA notes**, not App Store Connect uploads or production sign-off.

| File | What it records |
| --- | --- |
| [ios-release-symbol-proof-b9452205b.md](ios-release-symbol-proof-b9452205b.md) | Simulator Release `nm -Uj` empty matches for test-hook symbols on `b945220`; Debug contrast present for `beforeFinalSignatureDecision`. Unsigned local build; not installed. |

Re-run:

```bash
bash apps/ios/Scripts/verify_ios_release_symbols.sh
```
