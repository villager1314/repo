# 在 Termux 中使用 APKM / APKG

为标准 `com.termux` 安装提供专用包，路径为 `/data/data/com.termux/files/usr`。
Python 纯脚本包，Architecture: all；目标为 aarch64 和 x86_64 Termux。
没有在真实 Termux 设备上测试，欢迎先试 doctor 和本地 APK 安装。
不要把 Debian 的软件源加入原生 Termux；Termux 使用自己的 Python 和 ADB 包。
Termux 内的 Debian/Ubuntu PRoot 则继续使用对应的 Debian 包。

## 安装

在原生 Termux 中运行，无需 sudo：

```sh
pkg update
pkg install curl gpgv
mkdir -p "$PREFIX/share/keyrings" "$PREFIX/etc/apt/sources.list.d"
curl -fL https://villager1314.github.io/repo/keys/apkm.gpg -o "$PREFIX/share/keyrings/apkm.gpg"
```

通过可信渠道核对公钥指纹：

```text
C198FBB87F5D87047E86DD24995549BDF64D01F9
```

如需在设备上显示下载公钥的指纹，可安装 gnupg 后运行：

```sh
pkg install gnupg
gpg --show-keys --with-fingerprint "$PREFIX/share/keyrings/apkm.gpg"
```

添加专用源并安装：

```sh
printf 'deb [signed-by=%s/share/keyrings/apkm.gpg] https://villager1314.github.io/repo/termux/ ./\n' "$PREFIX" > "$PREFIX/etc/apt/sources.list.d/apkm.list"
apt update
apt install apkm
```

安装包会自动依赖 `python`、`android-tools`、`gpgv`。
需要手册时安装 `man`：`pkg install man`。

## 添加 APK 软件源

```sh
apkm source add personal https://villager1314.github.io/repo/android/ --keyring "$PREFIX/share/apkm-keyring.gpg"
apkm update
apkm --help
apkg --help
man apkm
```

初始 APK 源为空；添加自己的 APK 后才能按软件名安装。
已有 APK 文件可以直接安装。

## 无 root：通过无线 ADB 安装

安卓 11 或更高版本开启开发者选项中的无线调试。
先打开“使用配对码配对设备”，将设备显示的地址和端口代入：

```sh
adb pair IP:配对端口
adb connect IP:调试端口
adb devices
apkm doctor
apkg --mode adb install "$HOME/软件.apk"
apkm --mode adb install 软件名
```

配对码在终端交互输入，不写入 apkm 配置。
配对端口和调试连接端口不同，可能随无线调试开关变化。
部分设备可使用 127.0.0.1；优先采用设备无线调试页显示的 IP 地址。
存在多个 ADB 目标时在命令前加 `--serial IP:调试端口`。
在无 root 的 Termux 内直接执行 pm 通常没有安装权限，不能替代 ADB 授权。
安卓 11 以下可使用由电脑先启用的 TCP ADB 或宿主 root；本工具不自动开放端口。

## 有安卓宿主 root

```sh
apkg --mode root install "$HOME/软件.apk"
apkm --mode root install 软件名
```

首次使用 su 可能需要在 root 管理器中授权。
root 模式检查 su 是否得到安卓 uid=0，并通过 stdin 传 APK 给宿主 pm，
避免 Android 安装服务无法读取 Termux 私有文件的路径。
Linux/PRoot 的 root 不等于安卓 root；不能仅因提示符为 # 就判定有权限。

## 本地下载的 APK

Termux 私有目录下的文件可直接使用。下载目录访问若被拒绝，
按需执行 `termux-setup-storage` 并授权，再使用 `~/storage/downloads/软件.apk`。
无需为了软件源或 $HOME 下的 APK 申请共享存储权限。

## 构建

维护端：

```sh
python3 scripts/build_termux.py --key FINGERPRINT
```

或在没有 gpg-agent 的构建环境使用 PGPy：

```sh
python3 scripts/build_termux.py --private-key /私密路径/repository-private.asc
```

只发布 site/；私钥不能提交。Termux 包和 Debian 包名字相同，路径、依赖不同，
只能安装适用于当前环境的那一份。暂不支持更改包名或 PREFIX 的 Termux 分支。
