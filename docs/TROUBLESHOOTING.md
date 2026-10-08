# Troubleshooting

[README](../README.md) · [Termux guide](TERMUX.md)

| Symptom | Checks and next action |
| --- | --- |
| Wireless ADB pairing fails | Enable wireless debugging; reopen the pairing-code dialog and use its current pairing port with `adb pair IP:PORT`. Enter the displayed code. Then use the separate debugging port with `adb connect IP:PORT`. Both devices must be able to reach that address. |
| Device offline or unauthorized | Run `adb devices`; approve the Android authorization dialog. Reconnect using the current debugging port. Pairing and connection ports can change. |
| Multiple devices | Copy the intended serial from `adb devices`, then use `apkm --mode adb --serial SERIAL install NAME` or the corresponding removal command. |
| Repository fingerprint differs | Stop before importing or locally signing the key. Cross-check the full fingerprint through an independent trusted channel; investigate an announced key rotation with the maintainer. |
| GPG signature or hash failure | Retain the existing verified cache. Check the source URL and retry after mirror synchronization. Report source, time and exact error; do not disable signature verification. |
| APK signing conflict / UPDATE_INCOMPATIBLE | The installed app and new APK may have different signing keys, including upstream versus F-Droid builds. Continue using the original channel, or back up/export data before consciously switching. APKM does not auto-uninstall to bypass this. |
| No cache / stale search results | Run `apkm update SOURCE`. Search does not refresh automatically. `apkm source list` identifies configured sources. |
| Mirror rollback rejected | The mirror is older than the verified cached index. Wait for synchronization or retain the current source. |
| Duplicate app in multiple sources | Keep one source for the package; current catalog resolution rejects ambiguity. A source-priority/selection adapter is not implemented. |
| Linux root but installation denied | Use authorized ADB. Root installation requires Android host `su` and `pm`, not Linux/chroot/PRoot uid 0. |
| Termux gpgv says libgcrypt is too old | Try `apt install --only-upgrade libgcrypt libgpg-error`, then `gpgv --version` and `apt update`. If stale indexes cannot provide matching libraries, obtain the matching-architecture package from the official Termux source and validate it before manual recovery; see the Termux guide. |
| Termux wants clang/LLVM/pip | Install with `apt install --no-install-recommends apkm`. Runtime dependencies remain required. |
| Remove requests confirmation in scripts | Use `apkm --yes remove PACKAGE-ID`; global flags precede the command. Removal normally deletes data. |
| App still present after removal | Inspect the selected device and Android's returned error. APKM reports a failed absence check. Work profiles, managed apps and system components may require separate Android administration; automatic system-app removal is not provided. |

For a report, include client version, host environment, device Android version/ABI, backend, command and redacted output. Remove pairing codes, tokens and private keys. Include whether the error occurs with `apkg` directly. Physical-device behavior should be reported separately from mocked tests.
