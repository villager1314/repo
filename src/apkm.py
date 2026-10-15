#!/usr/bin/env python3
"""APKM/APKG 0.4.0: signed APK repository client and Android install backend."""
import argparse
import struct
import stat
import xml.etree.ElementTree as ET
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

VERSION = '0.4.0'
BASE_URL = 'https://villager1314.github.io/repo'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))) / 'apkm'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache'))) / 'apkm'
MAX_INDEX = 8 * 1024 * 1024

class Failure(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code

class Output:
    def __init__(self, args):
        self.args = args
    def event(self, stage, message, **data):
        if self.args.json:
            print(json.dumps(dict(stage=stage, message=message, **data), ensure_ascii=False), flush=True)
        else:
            print(f'[{stage}] {message}', flush=True)


def run(argv, check=True, **kw):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, **kw)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Failure(f'命令执行失败：{argv[0]}：{e}', 3) from e
    if check and p.returncode:
        raise Failure((p.stderr or p.stdout).strip() or f'{argv[0]} 退出码 {p.returncode}', 3)
    return p


def read_json(path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as e:
        raise Failure(f'无法读取配置：{path}: {e}', 2)


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def validate_url(url):
    if urllib.parse.urlparse(url).scheme != 'https':
        raise Failure('软件源和 APK 下载地址必须使用 HTTPS', 2)
    return url

class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit, out=None):
    validate_url(url)
    req = urllib.request.Request(url, headers={'User-Agent': f'apkm/{VERSION}'})
    with urllib.request.build_opener(HTTPSRedirect()).open(req, timeout=30) as r:
        chunks = []; done = 0; last = time.monotonic()
        while True:
            chunk = r.read(min(128*1024, limit + 1 - done))
            if not chunk: break
            chunks.append(chunk); done += len(chunk)
            if done > limit: break
            now = time.monotonic()
            if out and not out.args.no_progress and now-last >= 1:
                out.event('索引下载', f'{done / (1024*1024):.1f} MiB', bytes=done)
                last = now
        data = b''.join(chunks)
    if len(data) > limit:
        raise Failure('源索引或签名超过大小限制', 4)
    return data


def sources():
    return read_json(CONFIG/'sources.json', {})


def validate_index(index):
    if not isinstance(index, dict) or index.get('schema_version') != 1 or not isinstance(index.get('packages'), list):
        raise Failure('不支持的软件源索引格式', 4)
    seen = set()
    for p in index['packages']:
        if not isinstance(p, dict):
            raise Failure('软件条目必须是对象', 4)
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._+-]*', p.get('name', '')) or p['name'] in seen:
            raise Failure('软件名重复或不合法', 4)
        seen.add(p['name'])
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+', p.get('package_id','')):
            raise Failure('安卓包名不合法', 4)
        if type(p.get('version_code')) is not int or p['version_code'] < 1:
            raise Failure('version_code 必须是正整数', 4)
        if type(p.get('min_sdk')) is not int or p['min_sdk'] < 1:
            raise Failure('min_sdk 必须是正整数', 4)
        if not isinstance(p.get('version_name'), str):
            raise Failure('version_name 必须是字符串', 4)
        if not isinstance(p.get('abis'), list) or not p['abis'] or any(a not in ['any','arm64-v8a','armeabi-v7a','x86','x86_64'] for a in p['abis']):
            raise Failure('abis 必须包含有效安卓架构', 4)
        if not re.fullmatch('[0-9a-f]{64}', p.get('sha256','')):
            raise Failure('SHA256 不合法', 4)
        if type(p.get('size')) is not int or p['size'] <= 0:
            raise Failure('APK 大小必须为正整数', 4)
        if p.get('format','apk') not in {'apk','apkm','apks','xapk'}: raise Failure('不支持的软件包格式',4)
        if not isinstance(p.get('url'),str) or not p['url']:
            raise Failure('缺少 APK 地址', 4)
    return index


FDROID_FINGERPRINT = '37D2C98789D8311948394E3E41E7044E1DBA2E89'

def normalize_fdroid(data):
    """Convert the signed v1 index, retaining stable APK variants for selection."""
    if not isinstance(data.get('apps'), list) or not isinstance(data.get('packages'), dict):
        raise Failure('无效 F-Droid v1 索引', 4)
    result = []
    for app in data['apps']:
        package = app['packageName']
        suggested = app.get('suggestedVersionCode')
        variants = []
        for v in data['packages'].get(package, []):
            # Honor the maintainer's stable ceiling; never silently choose a beta.
            if suggested is None or int(v['versionCode']) > int(suggested):
                continue
            if v.get('hashType') != 'sha256' or not v.get('apkName', '').endswith('.apk'):
                continue
            item = dict(name=package, package_id=package,
                        description=app.get('name', app.get('localized', {}).get('en-US', {}).get('name', package)) + ' — ' + app.get('summary', app.get('localized', {}).get('en-US', {}).get('summary', '')),
                        version_code=int(v['versionCode']), version_name=v.get('versionName', ''),
                        min_sdk=int(v.get('minSdkVersion', v.get('sdkVersion', 1))), max_sdk=int(v.get('maxSdkVersion', 0)),
                        abis=[a for a in (v.get('nativecode') or ['any']) if a in ['any','arm64-v8a','armeabi-v7a','x86','x86_64']], sha256=v['hash'],
                        size=v['size'], url=v['apkName'], features=v.get('features', []))
            if item['abis'] and all(a in ['any','arm64-v8a','armeabi-v7a','x86','x86_64'] for a in item['abis']):
                validate_index(dict(schema_version=1, packages=[item]))
                variants.append(item)
        if variants:
            variants.sort(key=lambda v: v['version_code'], reverse=True)
            result.append(dict(variants[0], variants=variants))
    return dict(schema_version=1, revision=data['repo']['timestamp'], packages=result)


def select_variant(package, sdk=None, abis=None):
    for v in package.get('variants', [package]):
        if sdk is not None and (sdk < v['min_sdk'] or (v.get('max_sdk') and sdk > v['max_sdk'])):
            continue
        if abis is not None and 'any' not in v['abis'] and not set(abis) & set(v['abis']):
            continue
        return dict(v, source_url=package['source_url'])
    raise Failure(f'{package["name"]} 没有兼容设备的稳定 APK', 5)


def refresh(name, src, out):
    url = validate_url(src['url']).rstrip('/') + '/'
    fdroid = src.get('type') == 'fdroid'
    filename = 'index-v1.json' if fdroid else 'index.json'
    out.event('源', f'{name}：下载并验证索引')
    index = fetch(urllib.parse.urljoin(url, filename), 128 * 1024 * 1024 if fdroid else MAX_INDEX, out=out)
    sig = fetch(urllib.parse.urljoin(url, filename + ('.asc' if fdroid else '.sig')), 65536)
    key = Path(src['keyring'])
    if not key.is_file():
        raise Failure(f'缺少可信公钥：{key}', 4)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p/'index').write_bytes(index)
        (p/'sig').write_bytes(sig)
        result = run(['gpgv','--homedir',d,'--keyring',str(key.resolve()),str(p/'sig'),str(p/'index')],check=False)
        if result.returncode:
            raise Failure('APK 源签名验证失败，未更新缓存', 4)
    current = normalize_fdroid(json.loads(index)) if fdroid else validate_index(json.loads(index))
    target = CONFIG/'indexes'/f'{name}.json'
    previous = read_json(target)
    if type(current.get('revision')) is not int or current['revision'] < 1:
        raise Failure('索引 revision 必须为正整数',4)
    if previous and current['revision'] < previous['revision']:
        raise Failure('拒绝回退到旧版源索引',4)
    current['updated_at'] = int(time.time())
    current['source_url'] = src['url'].rstrip('/')
    write_json(target,current)
    out.event('源', f'{name}：签名验证通过，{len(current["packages"])} 个软件')


def catalog(out):
    result = {}
    configured = sources()
    if not configured:
        raise Failure('尚未添加 APK 源。运行 apkm source add --help 查看方法。',2)
    for name, src in configured.items():
        target = CONFIG/'indexes'/f'{name}.json'
        cached = read_json(target)
        if cached is None:
            raise Failure(f'{name} 没有本地索引，请先运行 apkm update {name}', 2)
        if cached.get('source_url', src['url'].rstrip('/')) != src['url'].rstrip('/'):
            raise Failure(f'{name} 的地址已改变，请先运行 apkm update {name}', 2)
        validate_index(cached)
        updated = cached.get('updated_at', int(target.stat().st_mtime))
        out.event('缓存', f'{name}：本地索引，更新于 {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(updated))}；刷新请运行 apkm update', updated_at=updated)
        for p in cached['packages']:
            if p['name'] in result:
                raise Failure(f'多个源包含同名软件 {p["name"]}，请保留一个对应源',2)
            result[p['name']] = dict(p, source_url=src['url'])
    return result

class Backend:
    def __init__(self, args, out):
        self.args, self.out = args, out
        self.mode, self.prefix = None, None
        adb_error = '未找到 adb'
        if args.mode in ('auto','adb') and shutil.which('adb'):
            p = run(['adb','devices'],check=False,timeout=20)
            devices=[]
            for line in p.stdout.splitlines():
                fields=line.split()
                if len(fields)==2 and fields[1]=='device':
                    devices.append(fields[0])
            if args.serial:
                if args.serial in devices:
                    self.prefix=['adb','-s',args.serial]
                else:
                    adb_error='所选设备未连接或未授权'
            elif len(devices)==1:
                self.prefix=['adb','-s',devices[0]]
            elif len(devices)>1:
                raise Failure('存在多个设备，请用 --serial 指定',3)
            else:
                adb_error='没有已授权 ADB 设备；请检查 adb devices'
            if self.prefix:
                self.mode='adb'
        if self.mode is None and args.mode in ('auto','root'):
            if args.serial:
                raise Failure('指定 --serial 时不会回退到本机 root',3)
            su='/system/xbin/su' if Path('/system/xbin/su').is_file() else '/system/bin/su'
            if not Path(su).is_file():
                su=shutil.which('su') or ''
            if Path('/system/bin/pm').is_file() and Path('/system/bin/getprop').is_file() and su:
                p=run([su,'-c','/system/bin/id -u'],check=False,timeout=15)
                if p.returncode==0 and p.stdout.strip()=='0':
                    self.prefix=[su,'-c']
                    self.mode='root'
        if self.mode is None:
            raise Failure(f'没有可用安装后端。ADB：{adb_error}；root 要求安卓宿主 su、pm、getprop 可用。Linux root 不等于安卓 root。',3)
        self.out.event('连接',f'后端 {self.mode}'+(f'，设备 {self.prefix[2]}' if self.mode=='adb' else '，安卓宿主 root'))

    def shell(self, args):
        if self.mode=='adb':
            # adb's remote shell parses a command string; quote every token.
            return run(self.prefix+['shell',shlex.join(args)],timeout=30)
        command=shlex.join(['/system/bin/'+args[0]]+args[1:])
        return run(self.prefix+[command],timeout=30)

    def device_info(self):
        sdk=self.shell(['getprop','ro.build.version.sdk']).stdout.strip()
        abis=self.shell(['getprop','ro.product.cpu.abilist']).stdout.strip()
        if not abis:
            abis=self.shell(['getprop','ro.product.cpu.abi']).stdout.strip()
        if not sdk.isdigit() or not abis:
            raise Failure('无法读取安卓 API 级别或 ABI',3)
        return int(sdk),abis.split(',')

    def installed(self):
        return [s.removeprefix('package:') for s in self.shell(['pm','list','packages']).stdout.splitlines() if s.startswith('package:')]

    def version(self, package):
        if self.mode=='adb':
            text=self.shell(['dumpsys','package',package]).stdout
        else:
            text=run(self.prefix+[shlex.join(['/system/bin/dumpsys','package',package])],timeout=30).stdout
        m=re.search(r'\bversionCode=(\d+)',text)
        return int(m[1]) if m else None

    def install(self,path):
        self.out.event('安装','进行中；安卓安装器未提供连续百分比')
        if self.mode=='adb':
            cmd=self.prefix+['install','-r',str(path.resolve())]
            p=run(cmd,check=False,timeout=300)
        else:
            # Stream bytes into pm: Linux container paths need not be visible to Android.
            command=f'/system/bin/pm install -r -S {path.stat().st_size}'
            with path.open('rb') as f:
                p=subprocess.run(self.prefix+[command],stdin=f,capture_output=True,timeout=300)
            p.stdout=p.stdout.decode(errors='replace')
            p.stderr=p.stderr.decode(errors='replace')
        if p.returncode or not any(line.strip()=='Success' for line in p.stdout.splitlines()):
            raise Failure((p.stderr+'\n'+p.stdout).strip() or '安卓未返回安装成功',5)
        self.out.event('安装','安卓返回 Success')

    def install_set(self,paths):
        if len(paths)==1: return self.install(paths[0])
        self.out.event('安装','整组 APK 安装中；签名一致性由 Android 验证')
        if self.mode=='adb':
            result=run(self.prefix+['install-multiple','-r']+[str(p.resolve()) for p in paths],check=False,timeout=600)
            if result.returncode or not any(line.strip()=='Success' for line in result.stdout.splitlines()):
                raise Failure((result.stderr+'\n'+result.stdout).strip() or '拆分 APK 安装失败',5)
        else:
            total=sum(p.stat().st_size for p in paths)
            result=run(self.prefix+[f'/system/bin/pm install-create -r -S {total}'],check=False,timeout=30)
            match=re.search(r'Success[^\n]*\[(\d+)\]',result.stdout)
            if result.returncode or not match: raise Failure('无法创建安卓安装会话：'+result.stdout+result.stderr,5)
            session=match[1]; committed=False
            try:
                for i,path in enumerate(paths):
                    command=f'/system/bin/pm install-write -S {path.stat().st_size} {session} part{i}.apk -'
                    with path.open('rb') as source:
                        result=subprocess.run(self.prefix+[command],stdin=source,capture_output=True,timeout=300)
                    if result.returncode or not result.stdout.strip().startswith(b'Success'):
                        raise Failure('写入安装会话失败：'+(result.stdout+result.stderr).decode(errors='replace'),5)
                result=run(self.prefix+[f'/system/bin/pm install-commit {session}'],check=False,timeout=300)
                if result.returncode or not any(line.strip()=='Success' for line in result.stdout.splitlines()):
                    raise Failure('提交安装会话失败：'+result.stdout+result.stderr,5)
                committed=True
            finally:
                if not committed:
                    try: run(self.prefix+[f'/system/bin/pm install-abandon {session}'],check=False,timeout=30)
                    except (Failure,OSError,subprocess.TimeoutExpired): pass
        self.out.event('安装','安卓返回 Success')

    def remove(self, package):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+',package):
            raise Failure('安卓包名不合法',2)
        if package not in self.installed():
            self.out.event('跳过',f'{package}: not installed',package_id=package)
            return
        self.out.event('卸载',f'{package}: uninstalling',package_id=package)
        if self.mode=='adb':
            p=run(self.prefix+['uninstall',package],check=False,timeout=120)
        else:
            p=run(self.prefix+[shlex.join(['/system/bin/pm','uninstall',package])],check=False,timeout=120)
        if p.returncode or p.stdout.strip()!='Success':
            raise Failure((p.stderr+'\n'+p.stdout).strip(),5)
        if package in self.installed():raise Failure(f'{package}: still installed after uninstall',5)
        self.out.event('卸载',f'{package}：Success',package_id=package)


def check_apk(path):
    try:
        with zipfile.ZipFile(path) as z:
            if 'AndroidManifest.xml' not in z.namelist():
                raise Failure('文件不是单 APK：缺少 AndroidManifest.xml',4)
    except (OSError,zipfile.BadZipFile) as e:
        raise Failure(f'无法读取 APK：{e}',4)



# Archive support is dependency-free. Android validates APK signing certificates at commit.
ARCHIVE_FORMATS = {'apkm', 'apks', 'xapk'}
MAX_ARCHIVE_BYTES = 8 * 1024**3
MAX_MANIFEST_BYTES = 8 * 1024**2
ABI_SPLITS = {'arm64_v8a':'arm64-v8a', 'armeabi_v7a':'armeabi-v7a', 'x86':'x86', 'x86_64':'x86_64'}
DENSITY_SPLITS = {'ldpi':120, 'mdpi':160, 'tvdpi':213, 'hdpi':240, 'xhdpi':320, 'xxhdpi':480, 'xxxhdpi':640}
ANDROID_NS = 'http://schemas.android.com/apk/res/android'


def archive_entries(z):
    infos=z.infolist()
    if len(infos)>2048: raise Failure('归档条目过多',4)
    seen=set(); total=0
    for entry in infos:
        name=entry.filename
        if name in seen or '\\' in name or name.startswith('/') or any(p in ('..','') for p in name.rstrip('/').split('/')) or ':' in name:
            raise Failure('归档存在重复或不安全路径',4)
        seen.add(name)
        if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
            raise Failure('不支持符号链接或加密归档',4)
        total+=entry.file_size
        if entry.file_size>2*1024**3 or total>MAX_ARCHIVE_BYTES:
            raise Failure('归档解压大小超过限制',4)
    apks=[i for i in infos if not i.is_dir() and i.filename.lower().endswith('.apk')]
    if not apks or len(apks)>512: raise Failure('归档缺少 APK 或包含过多 APK',4)
    if any(Path(name).name=='toc.pb' for name in seen):
        # Universal bundletool sets need no device targeting. Multi-variant protobuf
        # sets must be selected by bundletool, not guessed from filenames.
        if len(apks)!=1 or Path(apks[0].filename).name!='universal.apk':
            raise Failure('此 APKS 含 bundletool 多变体 toc.pb；请先用 bundletool extract-apks 按设备提取，或提供 universal APKS',4)
    return apks, any(i.filename.lower().endswith('.obb') for i in infos)


def manifest_elements(data):
    """Read relevant element attributes from Android binary XML (or text fixtures)."""
    if len(data)>MAX_MANIFEST_BYTES: raise Failure('AndroidManifest.xml 过大',4)
    if data.lstrip().startswith(b'<'):
        if b'<!DOCTYPE' in data or b'<!ENTITY' in data: raise Failure('不支持 XML 实体',4)
        root=ET.fromstring(data)
        return [(e.tag.rsplit('}',1)[-1],dict(e.attrib)) for e in root.iter()]
    def u16(o): return struct.unpack_from('<H',data,o)[0]
    def u32(o): return struct.unpack_from('<I',data,o)[0]
    if len(data)<8 or u16(0)!=3 or u16(2)!=8 or u32(4)!=len(data): raise Failure('无效二进制 AndroidManifest.xml',4)
    strings=[]; result=[]; offset=8
    while offset<len(data):
        if offset+8>len(data): raise Failure('XML chunk 截断',4)
        kind,header,size=struct.unpack_from('<HHI',data,offset)
        end=offset+size
        if header<8 or size<header or end>len(data): raise Failure('XML chunk 越界',4)
        if kind==1:
            if header<28: raise Failure('XML 字符串池头损坏',4)
            count=u32(offset+8); flags=u32(offset+16); start=offset+u32(offset+20)
            if count>100000 or offset+header+count*4>end or start<offset+header+count*4 or start>end: raise Failure('XML 字符串池越界',4)
            strings=[]
            def length(pos,utf8):
                if pos+(1 if utf8 else 2)>end: raise Failure('XML 字符串截断',4)
                first=data[pos] if utf8 else u16(pos); pos+=1 if utf8 else 2
                mask=0x80 if utf8 else 0x8000
                if first & mask:
                    if pos+(1 if utf8 else 2)>end: raise Failure('XML 字符串长度截断',4)
                    nxt=data[pos] if utf8 else u16(pos); pos+=1 if utf8 else 2
                    first=((first & (mask-1)) << (8 if utf8 else 16)) | nxt
                return first,pos
            for i in range(count):
                pos=start+u32(offset+header+i*4)
                if pos<start or pos>=end: raise Failure('XML 字符串偏移越界',4)
                if flags & 0x100:
                    _,pos=length(pos,True); n,pos=length(pos,True); width=1; enc='utf-8'
                else:
                    n,pos=length(pos,False); width=2; enc='utf-16le'; n*=2
                if pos+n+width>end or any(data[pos+n:pos+n+width]): raise Failure('XML 字符串截断',4)
                strings.append(data[pos:pos+n].decode(enc))
        elif kind==0x102:
            if header<16 or offset+header+20>end: raise Failure('XML 元素损坏',4)
            ext=offset+header
            def string(index):
                if index==0xffffffff: return ''
                if index>=len(strings): raise Failure('XML 字符串索引越界',4)
                return strings[index]
            tag=string(u32(ext+4)); attr_start=u16(ext+8); attr_size=u16(ext+10); count=u16(ext+12)
            pos=ext+attr_start
            if attr_start<20 or attr_size<20 or pos+count*attr_size>end: raise Failure('XML 属性越界',4)
            attrs={}
            for i in range(count):
                a=pos+i*attr_size; ns=string(u32(a)); name=string(u32(a+4)); raw=u32(a+8); typed_size=u16(a+12); typ=data[a+15]; value=u32(a+16)
                if typed_size!=8: raise Failure('XML 属性类型损坏',4)
                if raw!=0xffffffff: value=string(raw)
                elif typ==3: value=string(value)
                elif typ in (0x10,0x11,0x12): value=str(value)
                else: value=''
                key=('{'+ns+'}' if ns else '')+name
                if key in attrs: raise Failure('XML 属性重复',4)
                attrs[key]=value
            result.append((tag,attrs))
        offset=end
    return result


def apk_metadata(path):
    try:
        with zipfile.ZipFile(path) as z:
            if z.namelist().count('AndroidManifest.xml')!=1: raise Failure('APK Manifest 缺失或重复',4)
            if z.getinfo('AndroidManifest.xml').file_size>MAX_MANIFEST_BYTES: raise Failure('APK Manifest 过大',4)
            elements=manifest_elements(z.read('AndroidManifest.xml'))
            manifests=[a for tag,a in elements if tag=='manifest']
            if len(manifests)!=1: raise Failure('APK manifest 根节点无效',4)
            root=manifests[0]
            def android(attrs,key,default=''): return attrs.get('{'+ANDROID_NS+'}'+key,default)
            package=root.get('package',''); version=android(root,'versionCode'); major=android(root,'versionCodeMajor','0')
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+',package) or not version.isdigit() or not major.isdigit(): raise Failure('APK 包名或版本无效',4)
            split=root.get('split',''); target=android(root,'configForSplit',root.get('configForSplit',''))
            native={n.split('/')[1] for n in z.namelist() if n.startswith('lib/') and len(n.split('/'))>=3 and n.endswith('.so')}
            sdk=1
            for tag,attrs in elements:
                if tag=='uses-sdk':
                    value=android(attrs,'minSdkVersion','1')
                    if not value.isdigit(): raise Failure('不支持预览 SDK APK',4)
                    sdk=int(value)
            dependencies=[android(a,'name') for t,a in elements if t=='uses-split']
            if not re.fullmatch(r'[A-Za-z0-9_.-]*',split) or not re.fullmatch(r'[A-Za-z0-9_.-]*',target): raise Failure('APK split 名称无效',4)
            return {'path':path,'package':package,'version':int(version)+(int(major)<<32),'split':split,'target':target,'native':native,'min_sdk':sdk,'dependencies':dependencies}
    except (zipfile.BadZipFile,KeyError,struct.error,UnicodeError,ET.ParseError) as e:
        raise Failure(f'无法解析 APK 元数据：{e}',4)


def select_splits(items,backend):
    bases=[p for p in items if not p['split']]
    if len(bases)!=1: raise Failure('归档必须只有一个基础 APK；不支持多个独立变体',4)
    base=bases[0]; seen=set()
    for p in items:
        if (p['package'],p['version'])!=(base['package'],base['version']): raise Failure('拆分 APK 包名或版本不一致',4)
        if p['split'] in seen: raise Failure('拆分 APK 名称重复',4)
        seen.add(p['split'])
    sdk,abis=backend.device_info()
    abi_groups={}; density_groups={}; selected=[]
    for p in items:
        split=p['split']; token=split.rsplit('config.',1)[-1] if 'config.' in split else ''
        group=p['target'] or (split.split('.config.',1)[0] if '.config.' in split else '')
        if p['target'] and not token: raise Failure('无法识别配置拆分包的设备目标：'+split,4)
        if group=='base': group=''
        if token in ABI_SPLITS:
            abi_groups.setdefault(group,[]).append((ABI_SPLITS[token],p))
        elif token in DENSITY_SPLITS:
            density_groups.setdefault(group,[]).append((DENSITY_SPLITS[token],p))
        elif token and not re.fullmatch(r'[a-z]{2,3}(?:[._-]r[A-Z]{2}|-[A-Z][a-z]{3}(?:-[A-Z]{2})?)?',token):
            raise Failure(f'无法安全选择未知配置拆分包：{split}',4)
        else:
            # All language splits may coexist. Feature masters are retained and
            # uses-split dependencies are checked below.
            selected.append(p)
    if abi_groups:
        candidates=[abi for abi in abis if all(any(a==abi for a,_ in group) for group in abi_groups.values()) and all(not p['native'] or abi in p['native'] for p in selected)]
        if not candidates: raise Failure('没有覆盖所有模块的兼容 ABI',5)
        for group in abi_groups.values(): selected.append(next(p for a,p in group if a==candidates[0]))
    if density_groups:
        text=backend.shell(['wm','density']).stdout
        values=re.findall(r'(?:Physical|Override) density:\s*(\d+)',text)
        if not values: raise Failure('无法读取设备屏幕密度以选择 APK',3)
        density=int(values[-1])
        for group in density_groups.values(): selected.append(min(group,key=lambda pair:(abs(pair[0]-density),-pair[0]))[1])
    names={p['split'] for p in selected} | {'base'}
    for p in selected:
        if p['min_sdk']>sdk: raise Failure('APK 要求更高 Android API',5)
        if p['native'] and not p['native'].intersection(abis): raise Failure('APK 原生库与设备 ABI 不兼容',5)
        if p['target'] and p['target'] not in names: raise Failure('拆分包缺少目标模块',4)
        if any(n not in names for n in p['dependencies']): raise Failure('拆分包缺少依赖模块',4)
    return [base]+sorted((p for p in selected if p is not base),key=lambda p:p['split'])


def install_archive(path,backend,out):
    try:
        with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory(prefix='apkm-splits-') as temp:
            entries,obb=archive_entries(z)
            if obb: out.event('OBB 未安装','归档含 OBB；本版本仅安装 APK，游戏可能仍需扩展数据',obb_installed=False)
            items=[]
            for i,entry in enumerate(entries):
                target=Path(temp)/f'{i}.apk'
                with z.open(entry) as source, target.open('wb') as dest:
                    copied=0
                    for chunk in iter(lambda:source.read(128*1024),b''):
                        copied+=len(chunk)
                        if copied>entry.file_size: raise Failure('归档解压大小不符',4)
                        dest.write(chunk)
                if copied!=entry.file_size: raise Failure('归档解压文件截断',4)
                items.append(apk_metadata(target))
            selected=select_splits(items,backend)
            out.event('拆分选择',f'{len(selected)}/{len(items)} APK',splits=[p['split'] or 'base' for p in selected])
            backend.install_set([p['path'] for p in selected])
            if backend.version(selected[0]['package'])!=selected[0]['version']: raise Failure('归档安装后版本确认失败',5)
            out.event('结果','APK 安装成功'+('；OBB 未安装' if obb else ''),package_id=selected[0]['package'],obb_installed=False if obb else None)
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError) as e:
        raise Failure(f'无法读取 APK 归档：{e}',4)


def check_installable(path,format='apk'):
    if format=='apk': return check_apk(path)
    if format not in ARCHIVE_FORMATS: raise Failure('不支持的 APK 归档格式',4)
    try:
        with zipfile.ZipFile(path) as z: archive_entries(z)
    except zipfile.BadZipFile as e: raise Failure(f'无效 APK 归档：{e}',4)


def download(p,args,out):
    url=validate_url(urllib.parse.urljoin(p['source_url'].rstrip('/')+'/',p['url']))
    dest=Path(args.output_dir).expanduser() if args.output_dir else CACHE/'apks'
    dest.mkdir(parents=True,exist_ok=True)
    format=p.get('format','apk')
    final=dest/f'{p["name"]}-{p["version_code"]}-{p["sha256"][:12]}.{format}'
    if final.is_file() and final.stat().st_size == p['size']:
        digest = hashlib.sha256()
        with final.open('rb') as f:
            for chunk in iter(lambda: f.read(128*1024), b''): digest.update(chunk)
        if digest.hexdigest() == p['sha256']:
            check_installable(final,format)
            out.event('缓存', f'{p["name"]}：复用已校验 APK', path=str(final))
            return final
    fd,temp=tempfile.mkstemp(prefix='.download-',dir=dest)
    done=0; digest=hashlib.sha256(); start=time.monotonic(); last=0
    try:
        req=urllib.request.Request(url,headers={'User-Agent':f'apkm/{VERSION}'})
        with os.fdopen(fd,'wb') as f, urllib.request.build_opener(HTTPSRedirect()).open(req,timeout=30) as r:
            while True:
                data=r.read(128*1024)
                if not data: break
                done+=len(data)
                if done>p['size']:
                    raise Failure('下载大小超过签名索引声明',4)
                digest.update(data); f.write(data)
                now=time.monotonic()
                if now-last>=0.5:
                    if not args.no_progress:
                        out.event('下载',f'{p["name"]}：{done/p["size"]:.0%}，{done}/{p["size"]} 字节',bytes=done,total=p['size'],bytes_per_second=int(done/max(now-start,.001)))
                    last=now
        if done!=p['size'] or digest.hexdigest()!=p['sha256']:
            raise Failure('APK 大小或 SHA256 校验失败',4)
        check_installable(Path(temp),format)
        os.replace(temp,final)
        out.event('校验',f'{p["name"]}：大小和 SHA256 验证通过',path=str(final))
        return final
    finally:
        Path(temp).unlink(missing_ok=True)


def cleanup_apk(path, out):
    """Called only for repository downloads after successful version confirmation."""
    try:
        path.unlink(missing_ok=True)
        out.event('清理', '已删除安装成功的 APK', path=str(path))
    except OSError as e:
        # The Android install succeeded; report cleanup separately without lying about it.
        out.event('清理失败', f'应用已安装，APK 未能删除：{e}', path=str(path))



NIU_LAI_ART = '          /)             (\\\n         / |             | \\\n        /  |_____________|  \\\n        \\_/               \\_/\n     __/   __         __    \\__\n    /  \\  /  \\       /  \\   /  \\\n    \\__/  \\ o/       \\o /   \\__/\n       |      _______      |\n       |    /         \\    |\n       |   |  o     o  |   |\n        \\  |           |  /\n         \\  \\_________/  /\n          \\_____________/\n             /       \\\n            /         \\'
MAMA_ART = '       /\\\n      /  \\               /|\n      |   \\             / |\n       \\   \\____________/  |\n    ___/       ____       \\__\n   /   \\      /    \\   __   \\\n   \\__  |        (o)   (o)  |\n      \\ |             ______/\n       \\|           /       \\\n        |          /   o     |\n        |         |          |\n        |          \\________/\n         \\          \\______/\n          \\_______________/\n           /          \\\n          /            \\'


def parser(program):
    apkg=program=='apkg'
    language=os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG','en')
    def tr(zh,en): return zh if language.lower().startswith('zh') else en
    p=argparse.ArgumentParser(prog=program,epilog=None if apkg else 'This APKM has Niu Lai Powers.',description=tr('安卓本地 APK 安装后端','Local Android APK installation backend') if apkg else tr('签名 APK 软件源客户端（Linux x86-64 / ARM64）','Signed APK repository client (Linux x86-64 / ARM64)'))
    p.add_argument('--version',action='version',version=f'{program} {VERSION}')
    p.add_argument('--mode',choices=['auto','adb','root'],default='auto',help=tr('后端；auto 优先 ADB，再检查安卓宿主 root','Backend; auto prefers ADB, then checks Android host root'))
    p.add_argument('--serial',help=tr('ADB 设备序列号；多个设备时必须指定','ADB serial; required with multiple devices'))
    p.add_argument('--json',action='store_true',help=tr('逐行 JSON 事件，供其他程序读取','Emit newline-delimited JSON events'))
    p.add_argument('--no-progress',action='store_true',help=tr('只显示阶段日志','Show stage messages only'))
    p.add_argument('--yes',action='store_true',help=tr('跳过卸载确认，不绕过安卓授权','Skip uninstall confirmation, not Android authorization'))
    s=p.add_subparsers(dest='command',required=True)
    if not apkg:
        moo=s.add_parser('moo',help=tr('牛来字符画彩蛋','Niu Lai terminal easter egg'))
        moo.add_argument('variant',nargs='?',choices=['moo'])
    ins=s.add_parser('install',help=tr('安装本地 APK','Install local APKs') if apkg else tr('从软件源下载安装','Download and install repository APKs'))
    ins.add_argument('names',nargs='+',help=tr('本地 APK/APKM/APKS/XAPK 路径','Local APK/APKM/APKS/XAPK paths') if apkg else tr('软件名','Application names'))
    if not apkg:
        ins.add_argument('--keep-apk',action='store_true',help=tr('安装成功后保留下载的 APK；默认核对安装版本后删除','Keep APKs after successful installation; otherwise delete after version confirmation'))
        ins.add_argument('--download-only',action='store_true',help=tr('只下载并校验','Download and verify only'))
        ins.add_argument('--output-dir',help=tr('下载目录','Download directory'))
        search=s.add_parser('search',help=tr('搜索软件源','Search cached repositories')); search.add_argument('keyword')
        update=s.add_parser('update',help=tr('下载、验证签名并刷新本地索引','Download, verify and refresh local indexes')); update.add_argument('names',nargs='*',help=tr('指定源名；省略则刷新所有源','Source names; omit to update all sources'))
        upgrade=s.add_parser('upgrade',help=tr('更新源中可识别的应用','Upgrade installed applications found in repositories')); upgrade.add_argument('names',nargs='*'); upgrade.add_argument('--keep-apk',action='store_true',help=tr('更新成功后保留 APK','Keep APKs after successful upgrades')); upgrade.set_defaults(download_only=False,output_dir=None)
        source=s.add_parser('source',help=tr('管理软件源','Manage repositories')); sub=source.add_subparsers(dest='source_command',required=True)
        sub.add_parser('list')
        add=sub.add_parser('add'); add.add_argument('name'); add.add_argument('url'); add.add_argument('--type',choices=['apkm','fdroid'],default='apkm',help=tr('源索引格式','Repository index format')); add.add_argument('--keyring',help=tr('事先可信的 GPG 二进制公钥环路径','Previously trusted binary GPG keyring path'))
        change=sub.add_parser('set-url',help=tr('更换镜像并验证索引，保留可信公钥及回退检查','Verify and switch mirrors, preserving trust and rollback checks')); change.add_argument('name'); change.add_argument('url')
        remove=sub.add_parser('remove');remove.add_argument('name')
    info=s.add_parser('info',help=tr('查询安卓应用','Inspect an installed Android application') if apkg else tr('查询源中的软件','Inspect a repository application'));info.add_argument('name')
    s.add_parser('list',help=tr('列出设备上的应用','List applications on the device'))
    rem=s.add_parser('remove',help=tr('卸载安卓应用','Uninstall Android applications and their data')); rem.add_argument('names',nargs='+',help=tr('安卓包名','Android package IDs'))
    s.add_parser('doctor',help=tr('检查设备、权限及环境','Check device, permissions and environment'))
    return p


def invoke_apkg(path,args,out,operation="install"):
    executable=shutil.which('apkg')
    cmd=[executable] if executable else [sys.executable,str(Path(__file__).resolve()),'--as-apkg']
    cmd+=['--mode',args.mode,'--json']
    if args.serial:cmd+=['--serial',args.serial]
    if operation=='remove': cmd+=['--yes','remove']+list(path)
    else: cmd+=['install',str(path)]
    # Read events live; do not buffer all installation output until completion.
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    for line in proc.stdout:
        try:
            e=json.loads(line)
            stage=e.pop('stage');message=e.pop('message');out.event(stage,message,**e)
        except (ValueError,KeyError):
            out.event('卸载' if operation=='remove' else '安装',line.strip())
    stderr=proc.stderr.read(); code=proc.wait()
    proc.stdout.close();proc.stderr.close()
    if code:
        raise Failure(stderr.strip() or f'apkg {operation} failed',code)


def main(argv=None,program=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv[:1]==['--as-apkg']:
        program='apkg';argv=argv[1:]
    program=program or ('apkg' if Path(sys.argv[0]).name=='apkg' else 'apkm')
    args=parser(program).parse_args(argv);out=Output(args)
    try:
        if args.command=='moo':
            message=(MAMA_ART+'\n\n..."Niu Lai!"...') if args.variant else (NIU_LAI_ART+'\n\n..."Ma Ma!"...')
            if args.json: out.event('moo',message)
            else: print(message)
            return 0
        if args.command=='source':
            if args.source_command != 'list' and not re.fullmatch('[a-zA-Z0-9_-]+',args.name):
                raise Failure('源名仅允许字母、数字、下划线和连字符',2)
            all_sources=sources()
            if args.source_command=='list':
                out.event('源','已配置软件源',sources=all_sources)
                if not args.json:
                    for n,v in all_sources.items(): print(n,v['url'])
            elif args.source_command=='add':
                if not re.fullmatch('[a-zA-Z0-9_-]+',args.name):raise Failure('源名仅允许字母、数字、下划线和连字符',2)
                key=Path(args.keyring).expanduser().resolve() if args.keyring else Path(__file__).resolve().parent/'fdroid.gpg'
                if not args.keyring and (args.type != 'fdroid' or args.url.rstrip('/') not in ['https://f-droid.org/repo','https://mirrors.tuna.tsinghua.edu.cn/fdroid/repo','https://mirror.nyist.edu.cn/fdroid/repo']):
                    raise Failure('该源必须用 --keyring 指定事先可信的公钥',2)
                if not key.is_file():raise Failure('可信公钥环不存在',2)
                if args.name in all_sources:raise Failure('同名源已存在；请先删除',2)
                src={'url':validate_url(args.url).rstrip('/'),'keyring':str(key),'type':args.type}
                refresh(args.name,src,out)
                all_sources[args.name]=src;write_json(CONFIG/'sources.json',all_sources)
            elif args.source_command=='set-url':
                if args.name not in all_sources:raise Failure('软件源不存在',2)
                src=dict(all_sources[args.name],url=validate_url(args.url).rstrip('/'))
                refresh(args.name,src,out)
                all_sources[args.name]=src;write_json(CONFIG/'sources.json',all_sources)
            else:
                if args.name not in all_sources:raise Failure('软件源不存在',2)
                del all_sources[args.name];write_json(CONFIG/'sources.json',all_sources)
                (CONFIG/'indexes'/f'{args.name}.json').unlink(missing_ok=True)
            return 0
        if args.command=='update':
            configured=sources()
            if not configured:raise Failure('尚未添加 APK 软件源',2)
            selected=args.names or list(configured)
            for n in selected:
                if n not in configured:raise Failure(f'软件源不存在：{n}',2)
            for n in selected:refresh(n,configured[n],out)
            return 0
        if program=='apkm' and args.command in ['search','info','install','upgrade']:
            packages=catalog(out)
            if args.command=='search':
                for name,p in packages.items():
                    if args.keyword.lower() in (name+' '+p.get('description','')+' '+p['package_id']).lower():
                        out.event('软件',f'{name} {p["version_name"]} — {p.get("description", "")}',package=p)
                return 0
            if args.command=='info':
                if args.name not in packages:raise Failure('源中没有这个软件',2)
                out.event('软件',json.dumps(packages[args.name],ensure_ascii=False),package=packages[args.name]);return 0
            backend=None if args.download_only else Backend(args,out)
            if args.command=='upgrade' and not args.names:
                installed=set(backend.installed());args.names=[n for n,p in packages.items() if p['package_id'] in installed]
            for name in args.names:
                if name not in packages:raise Failure(f'源中没有 {name}',2)
                p=packages[name]
                if backend:
                    sdk,abis=backend.device_info()
                    p=select_variant(p,sdk,abis)
                    if p.get('features'):
                        available=set(line.removeprefix('feature:').split('=')[0] for line in backend.shell(['pm','list','features']).stdout.splitlines())
                        if not set(p['features']) <= available:raise Failure(f'{name} 缺少必需设备功能',5)
                    if sdk<p['min_sdk'] or ('any' not in p['abis'] and not set(abis)&set(p['abis'])):
                        raise Failure(f'{name} 不适用于设备 API {sdk} / {abis}',5)
                    version=backend.version(p['package_id'])
                    if args.command=='upgrade' and version is None:
                        out.event('跳过',f'{name} 未安装');continue
                    if version is not None and version>=p['version_code']:
                        out.event('跳过',f'{name} 已安装相同或更新版本');continue
                if not backend:p=select_variant(p)
                path=download(p,args,out)
                if backend:
                    args.mode=backend.mode
                    if backend.mode=='adb': args.serial=backend.prefix[2]
                    invoke_apkg(path,args,out)
                    actual=backend.version(p['package_id'])
                    if actual!=p['version_code']:raise Failure('安装后包名/版本与签名源声明不符',5)
                    out.event('结果',f'{name} 安装成功，versionCode={actual}')
                    if not args.keep_apk:
                        cleanup_apk(path,out)
            return 0
        if args.command=='remove':
            args.names=list(dict.fromkeys(args.names))
            for name in args.names:
                if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+',name):raise Failure('Invalid Android package ID: '+name,2)
            if not args.yes:
                if args.json or not sys.stdin.isatty():raise Failure('Uninstall requires --yes or interactive confirmation',2)
                if input('Uninstall apps and their data: '+', '.join(args.names)+'? Type yes: ')!='yes':raise Failure('Cancelled',1)
            if program=='apkm':
                invoke_apkg(args.names,args,out,operation='remove')
                return 0
        backend=Backend(args,out)
        if args.command=='doctor':
            sdk,abis=backend.device_info();out.event('检查',f'API {sdk}，ABI {", ".join(abis)}',sdk=sdk,abis=abis)
        elif args.command=='list':
            for package in backend.installed():out.event('应用',package,package_id=package)
        elif args.command=='info':
            version=backend.version(args.name)
            if version is None:raise Failure('应用不存在或无法读取版本',5)
            out.event('应用',f'{args.name} versionCode={version}',package_id=args.name,version_code=version)
        elif args.command=='install':
            for name in args.names:
                path=Path(name).expanduser()
                if path.suffix.lower().lstrip('.') in ARCHIVE_FORMATS: install_archive(path,backend,out)
                else: check_apk(path);backend.install(path)
        elif args.command=='remove':
            for name in args.names:backend.remove(name)
        return 0
    except Failure as e:
        if args.json:out.event('错误',str(e),exit_code=e.code)
        else:print(f'错误：{e}',file=sys.stderr)
        return e.code
    except (OSError,ValueError,subprocess.TimeoutExpired) as e:
        if args.json:out.event('错误',str(e),exit_code=1)
        else:print(f'错误：{e}',file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('已取消',file=sys.stderr);return 130

if __name__=='__main__':
    sys.exit(main())
