# Changelog

Versions below describe client behavior. Dates are omitted where the original release date was not recorded.

## Unreleased

- English default README and Chinese README with navigation, badges and architecture diagram.
- Troubleshooting, maintenance and contribution guides; issue and pull-request templates.
- CI checks and GitHub release publication with distinct Debian/Termux assets and checksums.

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
