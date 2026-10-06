# 验证结果（0.1.0）

已通过：
- 13 项自动检查，包括多设备拒绝、Linux root 与安卓 root 区分、SHA256 失败清理、真实源签名验证、篡改拒绝、revision 回退拒绝。
- 通过模拟的 ADB 设备运行完整下载 → 校验 → apkg 子进程 → adb install → 版本确认；模拟 APK 只用于测试，不会发布到软件源。
- 实际 dpkg-deb 构建与检查 Debian all 软件包。
- 实际 apt-get / apt-cache 在独立临时状态目录中分别验证 amd64 与 arm64 源签名、加载 Packages 并找到 apkm，不改变宿主 APT 配置。
- Arch 包 .PKGINFO、包文件列表、仓库数据库、SHA256 和全部 GPG 签名验证。
- 两份 man 手册使用 groff 渲染，无错误。

- Termux 专用包的 PREFIX 路径、依赖、解包后的两个命令启动、aarch64/x86_64 APT 索引加载和签名已通过构建端验证。

未验证：
- 没有真实 Termux 设备；安装、无线 ADB 和宿主 root 功能仍需实机测试。
- 没有连接真实安卓设备；ADB 安装和 root 直接安装尚需实机测试。
- 没有真实 Arch/pacman、ARM64 Linux 或 CachyOS；这些系统的安装和依赖解析未实机验证。
- 原有四个 Linux 源已在线验证；Termux 源本次发布后检查。
- 软件源没有真实 APK，需要维护者添加。

Arch 包和数据库按照 ALPM 归档格式生成；没有使用 makepkg/repo-add 构建，首次在 Arch 上发布前建议用 pacman 验证。
签名由构建端 PGPy 生成，客户端实际使用 gpgv/apt 验证通过。

## 0.2.0 F-Droid

16 automated tests passed. Verified real official index GPG signature against documented primary fingerprint; normalized 4478 stable applications. Downloaded com.zinaro.cachecleanerwidget (8947 bytes), verified signed SHA256, size and manifest; modified official index rejected. Four Linux repository signatures and isolated APT checks passed, as did Termux package checks. Actual Android installation and native Arch/Termux devices remain untested.

## 0.3.0 cache and Termux fixes

21 tests pass, including offline search/info with legacy 0.2.0 cache; missing-cache guidance without a network request; actual apkg subprocess install using the cached catalog; selected-source update; mirror failure preserving configuration; verified APK reuse and corrupt APK redownload. Existing actual-signature and rollback tests still pass. Four repository checks and isolated APT loading pass; Termux archive and APT aarch64/x86_64 checks pass. No physical Android device installation test.

## 0.3.1 automatic cleanup and source compatibility

28 tests pass: delete downloaded APK only after successful installed-version confirmation; keep on install failure/version mismatch, download-only or --keep-apk; cleanup failure reported separately; actual apkg subprocess install confirms cleanup. Mixed ABI regression tests pass. Existing cached-index, signature, rollback, and repository checks pass.
Actual remote indexes normalized: Izzy 1399 apps / 2957 variants; Guardian 16 / 38; microG 3 / 17; NewPipe 1 / 3. Diagnostic CMS signatures, entry manifests, and index-v2 hashes checked on all four sources; certificate fingerprints compared with official pages. microG current JSON/ASC pair failed GPG diagnostic validation; no key trusted or verification bypassed. Generic JAR production adapter remains unimplemented. No physical Android installation test.

## 0.3.3 removal and English help

35 tests pass, including offline removal delegation, batch validation before mutation, confirmation before backend access, duplicate IDs, absent-app skip, post-uninstall absence checks, and locale-selected help. English man pages rendered with groff; four repository signatures and isolated APT checks pass. Physical Android uninstall remains untested.
