# APKM / APKG 0.1.0

从签名 APK 软件源下载应用，通过 ADB 或安卓宿主 root 安装。
提供 Debian（amd64 / arm64）及 Arch（x86_64 / aarch64）四个软件源。
Python 实现不包含本机二进制，Debian 使用 all 包，Arch 使用 any 包。

## 发布到 GitHub Pages

1. 在 GitHub 新建公开仓库 `repo`，将本项目的内容上传到仓库根目录。
2. 默认分支为 main；Settings → Pages → Source 选择 GitHub Actions。
3. 自带工作流只发布 `site/`。不要把签名私钥上传到仓库。
4. 发布后入口为 https://villager1314.github.io/repo/ 。如果用户名或仓库名不同，替换本文和 site/index.html 中的 URL。

现有主页不受影响。此项目没有自动连接 GitHub，也尚未在线发布。
APK 源初始为空；不会默认转载第三方 APK。

## Debian 安装

先通过可信渠道核对 `site/keys/FINGERPRINT.txt` 中的公钥指纹。
下载 `https://villager1314.github.io/repo/keys/apkm.gpg`，执行：

```sh
sudo install -m 644 apkm.gpg /usr/share/keyrings/apkm.gpg
```

amd64 的 `/etc/apt/sources.list.d/apkm.list`：

```text
deb [arch=amd64 signed-by=/usr/share/keyrings/apkm.gpg] https://villager1314.github.io/repo/debian/amd64/ ./
```

arm64 使用：

```text
deb [arch=arm64 signed-by=/usr/share/keyrings/apkm.gpg] https://villager1314.github.io/repo/debian/arm64/ ./
```

```sh
sudo apt update
sudo apt install apkm
```

也可以先安装随附的本地 deb：`sudo apt install ./apkm_0.1.0-1_all.deb`。
包包含 apkm、apkg、两份 man 手册和 APK 源公钥。

## Arch / Arch Linux ARM 安装

核对指纹后导入公钥（将 FINGERPRINT 替换成实际指纹）：

```sh
sudo pacman-key --add apkm.gpg
sudo pacman-key --lsign-key FINGERPRINT
```

在 `/etc/pacman.conf` 末尾添加：

```ini
[apkm]
SigLevel = Required
Server = https://villager1314.github.io/repo/arch/$arch/
```

```sh
sudo pacman -Syu apkm
```

不关闭签名验证。CachyOS 的兼容性需在你的系统上另行验证。
Arch ARM 目标为 aarch64，不支持 32 位 armv7。

## 添加 APK 源及安装

```sh
apkm source add personal https://villager1314.github.io/repo/android/ --keyring /usr/share/apkm-keyring.gpg
apkm update
apkm search 关键字
apkm info 软件名
apkm install 软件名
apkm install --download-only 软件名
apkm upgrade
apkg install ./软件.apk
apkg list
apkg info com.example.app
apkg --yes remove com.example.app
apkm doctor
man apkm
man apkg
```

全局参数放在命令前：

```sh
apkm --mode adb --serial DEVICE install 软件名
apkg --mode root install ./软件.apk
apkg --json install ./软件.apk
```

ADB 模式需要设备授权。无线 ADB 先用 `adb pair 地址:配对端口` 和
`adb connect 地址:调试端口` 配对连接；两种端口可能不同。
Linux 的 root、chroot root 或 PRoot 模拟 root 不等于安卓宿主 root。
root 模式要求宿主 su、/system/bin/pm、getprop 可访问，并确认安卓 uid=0；
通过 stdin 向 pm 传 APK，避免把容器路径误当成安卓可访问路径。
若这些条件不成立，使用已授权的无线 ADB。
无 root 且无 ADB 授权时返回错误，不提供静默绕过。

## 添加自己的 APK

维护端安装 `aapt`，从 APK 自动读取包名、versionCode、SDK 和 ABI。
只添加有权分发的独立 APK；不改 APK 自身签名。

```sh
python3 scripts/add_apk.py 软件名 /路径/软件.apk --key FINGERPRINT --description '软件简介'
```

脚本复制 APK 到 `site/android/apks/`，更新 revision 和 SHA256，并重新签名。
提交更新的 site/android/ 即可部署。没有 APK 时目录含 .gitkeep。
只支持单 APK；不支持 split APK、APKS、XAPK 或 APKM 容器格式。
软件名 apkm 与 .apkm 容器格式没有关系。

## 重新构建

Debian/Ubuntu 构建端需要：python3、dpkg-dev、zstd、gnupg。

```sh
python3 scripts/build.py --key FINGERPRINT
python3 -m unittest discover -s tests -v
```

Linux 软件包及各源存放在 site/；构建中间文件存放在 build/。
本次已生成专用签名公钥；私钥另附私密备份文件，不能公开。
先导入该私钥或改用你自己的签名密钥再维护发布。
首次公开发布前可更换密钥；更换后重新构建并让客户端信任新公钥。

导入另附的备份：`gpg --import repository-private.asc`。
若构建环境无法启动 gpg-agent，可在构建端安装 PGPy，使用
`python3 scripts/build.py --private-key /私密路径/repository-private.asc`。
PGPy 仅为可选构建依赖，不是 apkm/apkg 的运行依赖。
项目中的 GitHub Actions 只发布已生成的网站，不读取签名私钥。

## 实现和限制

- apkm 实际启动 apkg 子进程，逐行读取 JSON 事件。
- 源索引使用 GPG detached signature；下载前验证签名及 APK 的 SHA256/大小。
- HTTPS 下载拒绝跳转到 HTTP；源索引有大小限制和 revision 回退检测。
- 多个 ADB 设备时要求 --serial，root 模式不会仅凭 Linux uid 判断权限。
- 下载显示真实字节数/速度；安装只显示状态和安卓返回结果。
- Android 管理已安装状态，apkm 不维护独立安装数据库。
- 不自动降级、不卸载重装绕过签名冲突；卸载默认要求确认。
- --json 输出每行一个事件，不是单个 JSON 文档。
- 本地 APK 安装检查 ZIP 和 Manifest 存在；实际签名及 APK 合法性由安卓验证。
- 索引的包名、SDK 和 ABI 由维护者提供；可信仓库仍需维护准确元数据。
- 无自动安装权限弹窗、断点续传、后台服务和第三方 APK 抓取。
- Linux/安卓设备 ABI 不同；下载选择依据目标安卓设备，而非 Linux CPU。

详见 VALIDATION.md：本环境没有真实安卓设备及 Arch/ARM64 系统，不能声称已在这些系统实机通过。
