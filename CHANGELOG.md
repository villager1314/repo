# Changelog

Versions below describe client behavior. Dates are omitted where the original release date was not recorded.

## Unreleased

- English default README and Chinese README with navigation, badges and architecture diagram.
- Troubleshooting, maintenance and contribution guides; issue and pull-request templates.
- CI checks and GitHub release publication with distinct Debian/Termux assets and checksums.

## 0.5.1

- Preserve F-Droid localized names, summaries and descriptions for cached search.
- Include display names in --names-only/--exact and show package IDs in results.
- Resolve unique full display names for repository install/download/reinstall/upgrade and info/version queries; reject ambiguity before device access.
- Run apkm update once after upgrading to refresh older normalized caches.

## 0.5.0

- Complete four scoped improvements with a per-item feasibility/results review.
- Add show/reinstall/download, local frontend installation, selected DPKG aliases, flexible common global options and strict long flags.
- Add repository list/filtering, richer info, local file inspection/contents and managed cache usage/cleaning.
- Add read-only simulations, explicit sources, numeric version selection, cached policy/versions and connection-scoped upgrade holds.
- Add optional official bundletool extraction for complex APKS; Java/JAR remain user-supplied.
- Change apkm list to repository entries; apkg list remains device applications.
- Retain Android signature enforcement, no automatic downgrade, OBB skipping and temporary cleanup.
- Document deferred features instead of providing no-op Debian commands.

## 0.4.2

- Show help and exit successfully when APKM/APKG is run without arguments.
- Add -v/--version and -y/--yes aliases; retain -h/--help.
- Help/version operations do not connect to Android or access repositories.

## 0.4.1

- Default APKM/APKG to ADB, allowing `apkg install PATH` without a mode flag.
- Keep root explicit and retain opt-in `--mode auto` fallback.
- Update CLI help and documentation examples.

## 0.4.0

- Install one-base APKM/APKS/XAPK archives through authorized ADB or Android host root.
- Parse binary Android manifests; select ABI/density splits and retain languages.
- Validate package/version/dependencies, archive limits and unsafe ZIP entries.
- Use ADB install-multiple or root sessions; abandon failed sessions and clean temporary files.
- Skip OBB with explicit warnings and confirm installed versions.
- Support signed custom-source archive format metadata and whole-archive hashes.
- Multi-variant bundletool toc.pb sets remain unsupported; universal APKS work.
- No new third-party runtime dependencies; physical-device validation remains pending.

## 0.3.5

- Keep the original front-facing Niu Lai art for `apkm moo`.
- Use the first side-facing Mama portrait for `apkm moo moo`, with the Niu Lai caption.

## 0.3.4

- Add offline `apkm moo` and `apkm moo moo` terminal easter eggs.

## 0.3.3

- Delegate APKM removal to APKG without repository access.
- Validate all package IDs before confirmation; deduplicate IDs and skip absent apps.
- Verify absence after successful removal; stop on first failure.
- Locale-selected English/Chinese CLI help and expanded English manuals.

## 0.3.2

- CLI help presentation update. No installation behavior changes.

## 0.3.1

- Delete downloaded APKs after successful installation and version confirmation.
- Add `--keep-apk`; retain failed installs and download-only files.
- Preserve supported ABIs in mixed F-Droid ABI lists.
- Document diagnostic checks and adaptation requirements for third-party APK sources.

## 0.3.0

- Search, info, install and upgrade use verified local index caches.
- Support selected-source updates, mirror URL replacement and legacy caches.
- Verify and reuse matching downloaded APKs.
- Document minimal Termux dependencies and library mismatch recovery.

## 0.2.0

- Add F-Droid JSON/GPG verification and stable device-compatible version selection.

## 0.1.0

- Initial APKM/APKG implementation, signed Debian/Arch repositories and local APK installation.
