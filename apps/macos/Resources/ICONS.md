# App icons (Mac App Store)

Copied from the RunSpecimen marketplace brand pack (do not redesign here):

- Source of truth (marketing site repo):
  `sites/runspecimen/public/brand/marketplace/macos/`
- Files: `AppIcon.icns`, `AppIcon-1024.png`, `AppIcon.iconset/*`

Requirements (verified by `Scripts/verify_app_icon.sh`):

- Square RGB PNGs, **no alpha**, field `#070A0F`
- Not pre-rounded (macOS applies the mask)
- Full iconset sizes through 512@2x / 1024

`Assets.xcassets/AppIcon.appiconset` must use the same `icon_<size>.png` /
`icon_<size>@2x.png` filenames (never Finder email-style names). 128×128@2× is
a 256×256 PNG. `verify_app_icon.sh` checks catalog `Contents.json`, pixel
sizes, and a warning-free `actool` compile.

`build_app.sh` copies `AppIcon.icns` into `Contents/Resources/`.
`Info.plist` sets `CFBundleIconFile` / `CFBundleIconName` = `AppIcon`.
