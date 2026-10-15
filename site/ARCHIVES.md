# APKM / APKS / XAPK archives (0.4.0)

[English README](../README.md) · [中文 README](../README.zh-CN.md)

## Commands

```sh
apkg --mode adb install ./application.apkm
apkg --mode adb --serial DEVICE install ./application.apks
apkg --mode root install ./application.xapk
```

Global options precede the command. File arguments are local to the machine running APKG, including when ADB targets another device. Local archives are retained. Temporary extracted APKs are deleted after success, failure or interruption.

## Supported layouts

| Layout | Support |
| --- | --- |
| APKM / XAPK / APKS containing one base APK and configuration/feature splits | Supported within the selection rules below |
| XAPK containing one standalone APK | Supported |
| XAPK with OBB files | Install APKs only; emit an explicit OBB-not-installed event |
| bundletool universal APKS, one universal.apk plus toc.pb | Supported |
| bundletool multi-device/multi-variant toc.pb APKS | Rejected; use bundletool extract-apks with a device spec first |
| Multiple standalone base variants, encrypted archives, unknown configuration targeting | Rejected |
| AAB, asset packs / Play Asset Delivery and installing OBB data | Not implemented |

The file extension alone is not a compatibility guarantee. There is no universal metadata format across all APKM/APKS/XAPK producers. A single base APK must be present. Package ID, long versionCode and split names are read from the APK manifests, rather than trusted from filenames or archive JSON.

## Device selection

- Read Android API and ABI preference order from the selected target.
- Recognize common config ABI names: arm64_v8a, armeabi_v7a, x86 and x86_64. Select the first device ABI available across ABI-targeted modules.
- Recognize ldpi/mdpi/tvdpi/hdpi/xhdpi/xxhdpi/xxxhdpi. Use the closest available numeric density per module; ties prefer higher density. This simple policy does not reproduce all Android resource-qualifier targeting rules.
- Keep language splits together; feature masters and declared uses-split dependencies are checked.
- Reject unknown config targeting, duplicate split names, incompatible native libraries, missing dependencies and mismatched package IDs/versions. Complex feature-delivery targeting is not implemented.

Package signatures are checked by Android when the installation session is committed. APKG does not independently verify APK signing certificates in Python or bypass update-signature checks.

## Backends

ADB installs a selected set with `adb install-multiple -r`. Android host root creates an install session with `pm install-create`, streams each APK through `pm install-write`, then uses `pm install-commit`. A failed write/commit attempts `pm install-abandon`. Ordinary single APKs retain the existing installation path.

Archive installation is reported successful only after Android Success and an installed-version check. APK files within a single archive form one install operation; separate file arguments are processed in order and earlier successes are not rolled back after a later failure.

## OBB and cleanup

OBB files are not extracted or deployed. An archive containing an `.obb` file prints a warning before installation and an APK-success/OBB-not-installed result afterward. A successful exit means the APK installation succeeded; it does not mean game resources are complete. Games may download missing data or fail to launch without it.

Local input files are never deleted. Source-downloaded archives follow existing cleanup behavior: delete only after success and the repository version check, unless `--keep-apk` is set. Failure and `--download-only` retain downloads. Temporary extraction is separate and always cleaned.

## Self-hosted repositories

Custom signed schema-1 entries may declare `"format": "apkm"`, `"apks"` or `"xapk"`; omitted format means `apk`. SHA256 and size must describe the entire archive. Package ID/version/API/ABI metadata describe the application inside. Downloads preserve the declared extension and verify signed size/hash before use. The maintainer helper `scripts/add_apk.py` still adds standalone APKs only; archive entries must be prepared and signed by the maintainer. F-Droid normalization continues to select standalone APKs.

## Limits and validation

At most 2048 ZIP entries, 512 APKs, 2 GiB per entry and 8 GiB total declared uncompressed size. Duplicate names, unsafe paths, symlinks and encrypted entries are rejected. Extraction writes generated temporary filenames, never archive-supplied paths. Only the APK entries are extracted. The complete APK set is extracted before selection, so allow enough local temporary storage.

Binary Android XML and text XML manifests are parsed using the Python standard library. An actual F-Droid APK was used to check binary metadata parsing. Automated tests use synthetic archives and a simulated ADB subprocess, plus root session failure tests. Physical-device installs, real third-party split signing and Android/OEM differences still need validation.

Official bundletool reference: https://developer.android.com/tools/bundletool

## 中文速览

本版安装归档中的 APK，不安装 OBB。ADB 和安卓 root 都支持，原始本地文件保留，临时解压自动清理。默认选择目标设备兼容 ABI、最接近密度并保留语言包。要求单个基础 APK，包名版本一致，最终签名由 Android 验证。标准 bundletool 多设备变体 APKS 暂不直接解析 toc.pb；请先按设备提取，或使用 universal APKS。没有新增第三方运行依赖，仍需实机验证。
