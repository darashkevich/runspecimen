# RunSpecimen IntelliJ plugin (scaffold)

Minimal Tools-menu adapter. Requires JDK 17+ and the JetBrains IntelliJ Gradle
plugin network access on first build.

```bash
cd plugins/runspecimen/jetbrains/intellij-plugin
./gradlew buildPlugin   # after generating the Gradle wrapper locally
```

If the wrapper is missing:

```bash
gradle wrapper --gradle-version 8.7
./gradlew buildPlugin
```

Install the ZIP from `build/distributions/` via **Settings → Plugins → Install
Plugin from Disk**.

## Approve-safety

- No Approve action in `plugin.xml`.
- `RequestApprovalAction` only displays the human TTY command via
  `ide_actions.py request-approval`.
- Kotlin helper refuses action names `approve` / `remote-confirm`.

JetBrains Marketplace submission is **out of scope** for this PR.
