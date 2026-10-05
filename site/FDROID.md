# F-Droid 源（apkm 0.2.0）

Debian、Arch 和 Termux 使用相同命令：

```sh
apkm source add fdroid https://f-droid.org/repo --type fdroid
apkm search termux
apkm info com.termux
apkm install com.termux
```

已有自建 APK 源可以保留。应用名使用 Android 包名。无需把 F-Droid APK 上传到 GitHub Pages。

只下载、不连接设备：

```sh
apkm install --download-only --output-dir ./apks com.termux
```

下载模式选最新稳定 APK；存在多个架构时，未连接设备不能保证适合你的手机。安装模式按设备 API、ABI 和必需功能检查，允许选择兼容的旧稳定版本；不支持 split APK。

验证官方 `index-v1.json.asc` 的 GPG 签名，再检查每个 APK 的大小和 SHA256。内置官方公钥指纹为 `37D2C98789D8311948394E3E41E7044E1DBA2E89`，来源： https://f-droid.org/docs/Release_Channels_and_Signing_Keys/ 。时间戳倒退或签名失败时拒绝替换缓存。每次查询会重新验证完整索引，首次下载约 64 MB；当前尚未实现增量更新。

第三方 F-Droid 格式源须提供事先可信的二进制 GPG 公钥环：

```sh
apkm source add other https://example.org/fdroid/repo --type fdroid --keyring ./trusted.gpg
```

第三方源必须提供 `index-v1.json` 和 `.asc`；仅提供签名 JAR 的源暂不支持。不要仅凭下载地址信任第三方公钥。

无 root 用已授权 ADB（Termux 可用无线调试）；安卓宿主有 root 可指定 `apkm --mode root install 包名`。安装进度沿用实际下载字节和 Android 返回状态。
