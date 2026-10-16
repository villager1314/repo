# Command guide (0.5.0)

[README](../README.md) · [Four-step feasibility review](FOUR-STEPS.md)

APKM manages repositories and plans downloads/updates. APKG installs or queries a selected Android target. ADB remains the default; root is explicit. These tools implement a useful subset of APT/DPKG conventions, not their Debian dependency or filesystem model.

## Repository commands

```sh
apkm show com.example.app
apkm search example app --names-only
apkm search com.example.app --exact
apkm list 'com.example.*'
apkm list --installed
apkm list --upgradable
apkm versions com.example.app
apkm policy com.example.app --source fdroid
apkm download com.example.app --output-dir ./downloads
apkm -d install com.example.app
apkm reinstall com.example.app
apkm install com.example.app=123 --source fdroid
apkm install ./application.apkm
apkm remove friendly-name -y
```

`show` aliases `info`. Ordinary info/show output uses readable fields; JSON retains metadata. `download` means download and integrity-check, without an Android connection; ABI selection cannot be guaranteed without a target. `reinstall` permits equal versionCode, but never silently downgrades. Available versions are limited to those retained in the verified index; version selection uses decimal versionCode, not a potentially ambiguous versionName.

`list` now lists cached repository entries without connecting to Android. `--installed` and `--upgradable` list only apps known to those repositories; use `apkg list` for all installed package IDs. `versions` lists retained variants, including ABI alternatives. `policy` shows cached candidate/source data, not a live installed-state or signature comparison. Select `--source NAME` when duplicate names exist; automatic source priority and cross-signer migration are not implemented.

Local paths go directly to APKG without a repository index. Local and repository arguments must be installed in separate commands. Removal accepts Android IDs directly without an index. Non-ID friendly source names need a valid cached catalog; if a name is itself a valid Android ID, it is treated as an ID unless an explicit source mapping is requested.

## APKG and DPKG-style aliases

| Command | Alias | Meaning |
| --- | --- | --- |
| install PATH ... | -i / --install | Install local files |
| remove ID ... | -r / --remove | Remove apps and normally their data |
| list [PATTERN] | -l / --list | List device package IDs |
| info ID / status ID | -s / --status | Installed versionCode and APK paths |
| file-info PATH | -I / --info | Inspect local APK/archive metadata offline |
| contents PATH | -c / --contents | List ZIP entries offline |

```sh
apkg -i ./application.apk
apkg -r com.example.app -y
apkg -l 'com.example.*'
apkg list --system
apkg list --user-apps
apkg -s com.example.app
apkg -I ./application.xapk
apkg -c ./application.apkm
```

`apkg info` queries a device; `apkg --info` inspects a local file. Local metadata does not prove signing trust or device compatibility. DPKG -L/-S/-V, extracting to arbitrary directories and Debian configure/triggers are not implemented. No claim is made to enumerate Android app-private data files.

## Preview and holds

```sh
apkm install com.example.app -s
apkm upgrade --simulate
apkg install ./application.apkm --dry-run
apkg remove com.example.app --simulate
apkm clean --simulate
apkm hold com.example.app
apkm showhold
apkm unhold com.example.app
```

Preview supports install/reinstall/download, upgrade, remove and clean. It does not download, install, uninstall or clean files. Other mutating commands reject the simulation flag. Source install previews may query the device to choose candidates. Local-file previews inspect metadata offline, without fully selecting splits for the target or verifying Android signatures. Real installs emit a per-item plan before acting; there is no atomic multi-app transaction or rollback.

Holds apply only to APKM `upgrade`, not explicit install/reinstall or other installers. They are saved in `holds.json`, scoped to the ADB connection serial or local root connection. Wireless IP/port changes produce a different scope; a hold is not a permanent hardware identity or system-wide lock. Hold commands require Android package IDs.

## Cache management

```sh
apkm cache-info
apkm clean -y
```

Only regular files with APKM's generated download filename pattern under its download cache are counted/removed. Indexes, arbitrary filenames, symlinks and files in custom output directories are retained. Clean prompts unless -y is present (empty cache returns directly). It never deletes installed applications.

## Parameters

Common global options may appear before or after the subcommand. `--` stops option handling and protects literal filenames. Incomplete long-option abbreviations are rejected. Help: -h, -?, --help; version: -v/--version; confirmation: -y/--yes. APKM uses -s for simulation, while APKG uses -s for installed status; use APKG --simulate/--dry-run for preview.

## Optional bundletool

```sh
apkg install ./multivariant.apks --bundletool /trusted/path/bundletool-all.jar
```

Supply an official bundletool JAR and an installed Java runtime yourself. Neither is automatically downloaded or added as a default dependency. APKG constructs a device specification from API/ABI/density/locales, invokes official extract-apks, validates its resulting APK set and then uses the existing ADB/root installer. This optional bridge does not implement the protobuf selection engine itself, and does not add asset-pack/OBB installation. See [archive details](ARCHIVES.md).
