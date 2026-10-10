#!/usr/bin/env python3
"""APKM/APKG 0.3.1: signed APK repository client and Android install backend."""
import argparse
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

VERSION = '0.3.4'
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


def download(p,args,out):
    url=validate_url(urllib.parse.urljoin(p['source_url'].rstrip('/')+'/',p['url']))
    dest=Path(args.output_dir).expanduser() if args.output_dir else CACHE/'apks'
    dest.mkdir(parents=True,exist_ok=True)
    final=dest/f'{p["name"]}-{p["version_code"]}-{p["sha256"][:12]}.apk'
    if final.is_file() and final.stat().st_size == p['size']:
        digest = hashlib.sha256()
        with final.open('rb') as f:
            for chunk in iter(lambda: f.read(128*1024), b''): digest.update(chunk)
        if digest.hexdigest() == p['sha256']:
            check_apk(final)
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
        check_apk(Path(temp))
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



NIU_LAI_ART = r"""          /)             (\
         / |             | \
        /  |_____________|  \
        \_/               \_/
     __/   __         __    \__
    /  \  /  \       /  \   /  \
    \__/  \ o/       \o /   \__/
       |      _______      |
       |    /         \    |
       |   |  o     o  |   |
        \  |           |  /
         \  \_________/  /
          \_____________/
             /       \
            /         \
""".rstrip()

# Hand-drawn 女 + 马 strokes, doubled to form 妈妈. ASCII only, no font dependency.
MAMA_GLYPH = (
    "   #     #######",
    "   #           #",
    "   #       #   #",
    "#######    #   #",
    "  #   #    #####",
    "  #   #    #    ",
    " #    #    #####",
    "  #  #         #",
    "   ##    ##### #",
    "  #  #         #",
    " #    #       # ",
    "#            #  ",
)
MAMA_ART = '\n'.join(row + '   ' + row for row in MAMA_GLYPH)


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
    ins.add_argument('names',nargs='+',help=tr('本地 APK 路径','Local APK paths') if apkg else tr('软件名','Application names'))
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
            message=NIU_LAI_ART
            if args.variant: message+='\n\n'+MAMA_ART+'\n\n..."Niu Lai!"...'
            else: message+='\n\n..."Ma Ma!"...'
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
                path=Path(name).expanduser();check_apk(path);backend.install(path)
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
