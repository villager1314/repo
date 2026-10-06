# 其他开源 APK 源适配实测

检查日期：2026-10-06。工具版本：apkm 0.3.1。

此次实际请求了下列源的 index-v1.json、签名文件、index-v1.jar、entry.jar、entry.json 和 index-v2.json。解析的是实际索引，未在安卓真机上安装这些源的 APK。

**解析兼容不等于已安全接入。0.3.1 的生产客户端仍仅支持自建 APKM 签名索引和 F-Droid JSON + GPG 签名；尚未实现通用 JAR 验签。**

| 源 | 地址 | 实际索引解析 | 当前阻碍 | 所需适配 |
| --- | --- | --- | --- | --- |
| IzzyOnDroid | https://apt.izzysoft.de/fdroid/repo/ | 1399 应用、2957 个稳定 APK 变体 | 本次 .asc/.sig 请求均为 404；有签名 JAR | JAR 验签及固定发布者 X.509 证书 SHA256；混合 ABI 已修复；多源同包选择 |
| Guardian Project | https://guardianproject.info/fdroid/repo/ | 16 应用、38 个稳定 APK 变体 | 本次 .asc/.sig 请求均为 404；有签名 JAR | JAR 验签及固定官方证书；混合 ABI 已修复；多源同包选择 |
| microG | https://repo.microg.org/fdroid/repo/ | 3 应用、17 个稳定 APK 变体 | .asc 存在，但本次下载的配对索引验签为 BAD signature；有签名 JAR | 改用 JAR 验签、固定官方证书；区分 APK 安装与系统签名伪装/系统组件配置 |
| NewPipe 上游 | https://archive.newpipe.net/fdroid/repo/ | 1 应用、3 个稳定 APK 变体 | 本次 .asc/.sig 请求均为 404；有签名 JAR | JAR 验签、固定官方证书；多源同包选择及不同 APK 签名的更新兼容性 |
| GitHub Releases（以 termux/termux-app 为例） | https://github.com/termux/termux-app/releases | 实际请求 latest API，返回 v0.118.3、6 个 release assets | 不是 F-Droid/APKM 索引；无统一包名、versionCode、minSdk 元数据格式 | GitHub API 适配器、稳定版/预发布筛选、架构资产选择、AndroidManifest 元数据解析、发布者及 APK 签名/摘要信任策略、缓存和限流处理 |

## 已在 0.3.1 修复：混合 ABI 条目

Guardian 和 Izzy 的部分 APK 同时带有 arm64-v8a 等有效架构与 armeabi、mips、mips64、x86_64/darwin 等额外条目。旧版会因任一陌生条目而排除整个 APK。

新版保留 arm64-v8a、armeabi-v7a、x86、x86_64 和 any，忽略其他 ABI；过滤后完全没有支持架构才跳过该 APK。不会把未知架构误判为通用 APK。

解析覆盖从 Izzy 的 1388 个应用提升到 1399 个，Guardian 从 13 个提升到 16 个。此项修复已包含回归测试。

## JAR 路线的实际检查范围

四个源均提供签名 index-v1.jar 和 entry.jar。我们实际检查了 entry.jar 的 PKCS#7/CMS 签名、签名文件对 MANIFEST.MF 的 SHA256，以及 manifest 对 entry.json 的 SHA256，再下载 index-v2.json 检查 signed entry 声明的大小和 SHA256；四个源的这些检查均通过。

上述检查是针对观察到的四个文件布局的诊断，**不是生产客户端实现**，也不是仅凭内嵌证书就建立发布者信任。四个源下载证书的指纹均与维护者官网发布的指纹一致；Izzy 的指纹位于官网添加源链接的 fingerprint 参数中。生产客户端尚未加入这些可信证书及通用 JAR 验签路径。

| 源 | 本次观测到的 JAR 证书 SHA256 |
| --- | --- |
| IzzyOnDroid | 3BF0D6ABFEAE2F401707B6D966BE743BF0EEE49C2561B9BA39073711F628937A |
| Guardian Project | B7C2EEFD8DAC7806AF67DFCD92EB18126BC08312A7F2D6F3862E46013C7A6135 |
| microG | 9BD06727E62796C0130EB6DAB39B73157451582CBD138E86C468ACC395D14165 |
| NewPipe | E2402C78F9B97C6C89E97DB914A2751FDA1D02FE2039CC0897A462BDB57E7501 |

完整适配应按顺序：固定可信证书 → 验证 JAR 的签名及每个目标条目摘要 → 解析索引 → 保留版本回退检查 → 缓存。ZIP 重名条目、未签名目标、异常 manifest、弱算法或错误摘要都必须拒绝。

可先实现 index-v1.jar，复用现有 JSON 解析器；JAR 本身压缩，Izzy 本次约 3.7 MB，明显小于约 15.7 MB 的裸 v1 JSON。
后续实现 entry.jar + index-v2，再支持增量 diff，可进一步减少更新流量。查询仍只读已验证缓存。

生产实现可研究经过验证的 JAR 库或 OpenSSL CMS 配合严格的 JAR manifest 验证；不要仅 unzip JSON，也不要只检查证书指纹。避免为了一个小工具默认拉入整个 JDK。

## microG 的 GPG 检查

旧地址 https://microg.org/fdroid/repo/ 与官网推荐地址 https://repo.microg.org/fdroid/repo/ 本次均返回相同 v1 JSON 和 .asc。签名文件注明的时间为 2022-10-21，JSON 的 repo.timestamp 对应 2026 年。

按签名声明的指纹 22F796D6E62E6625A0BCEFEA7F979A66F3E08422 从公开密钥目录取回公钥，仅作诊断，再执行 gpgv，得到 BAD signature。该密钥没有加入 apkm 的可信列表。此结果只说明本次响应中的索引/签名不匹配，不能推断后续服务状态或绕过验签。

## 多源同包和安装能力

F-Droid 主源与 NewPipe、Guardian、Izzy 等源可能包含同一个 Android 包。当前 apkm 遇到同名软件会明确报错；后续需要显式 --source 或源优先级以及 signer 兼容性判断，不能静默混用不同发布者的 APK。

NewPipe 官网说明其上游 APK 与 F-Droid 构建签名可能不同。适配器不应自动卸载旧应用或删除用户数据；Android 的签名兼容性检查仍必须保留。

microG APK 下载与安装，并不意味着自动完成系统签名伪装或替换系统组件。普通 ADB 安装也不能代替这些系统配置。

## 官方资料

- IzzyOnDroid：https://apt.izzysoft.de/fdroid/
- Guardian 仓库与签名指纹：https://guardianproject.info/fdroid/index.html
- microG 官方仓库信息：https://microg.org/fdroid/repo/
- NewPipe 添加官方源：https://newpipe.net/FAQ/tutorials/install-add-fdroid-repo/
- F-Droid 索引 API：https://f-droid.org/en/docs/All_our_APIs/
- JAR 签名格式：https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html
- GitHub Releases API：https://docs.github.com/en/rest/releases/releases
