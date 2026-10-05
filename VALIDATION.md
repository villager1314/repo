# 验证结果（0.1.0）

已通过：
- 11 项自动检查，包括多设备拒绝、Linux root 与安卓 root 区分、SHA256 失败清理、真实源签名验证、篡改拒绝、revision 回退拒绝。
- 通过模拟的 ADB 设备运行完整下载 → 校验 → apkg 子进程 → adb install → 版本确认；模拟 APK 只用于测试，不会发布到软件源。
- 实际 dpkg-deb 构建与检查 Debian all 软件包。
- 实际 apt-get / apt-cache 在独立临时状态目录中分别验证 amd64 与 arm64 源签名、加载 Packages 并找到 apkm，不改变宿主 APT 配置。
- Arch 包 .PKGINFO、包文件列表、仓库数据库、SHA256 和全部 GPG 签名验证。
- 两份 man 手册使用 groff 渲染，无错误。

未验证：
- 没有连接真实安卓设备；ADB 安装和 root 直接安装尚需实机测试。
- 没有真实 Arch/pacman、ARM64 Linux 或 CachyOS；这些系统的安装和依赖解析未实机验证。
- GitHub Pages 未上线，尚未验证公开 URL 和目标网络访问。
- 软件源没有真实 APK，需要维护者添加。

Arch 包和数据库按照 ALPM 归档格式生成；没有使用 makepkg/repo-add 构建，首次在 Arch 上发布前建议用 pacman 验证。
签名由构建端 PGPy 生成，客户端实际使用 gpgv/apt 验证通过。
