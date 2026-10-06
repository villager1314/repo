#!/usr/bin/env python3
"""Build packages and a GitHub Pages tree. Requires gpg, dpkg-deb, dpkg-scanpackages, zstd."""
import argparse, base64, gzip, hashlib, io, json, os, shutil, subprocess, tarfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
VER='0.3.1'
PGP_KEY=None
def call(cmd,**kw):return subprocess.run(cmd,check=True,**kw)
def sign(path,key):
 if PGP_KEY is not None:
  Path(str(path)+'.sig').write_bytes(bytes(PGP_KEY.sign(path.read_bytes())))
  return
 call(['gpg','--batch','--yes','--local-user',key,'--detach-sign','--output',str(path)+'.sig',str(path)])
def build(key,private_key=None):
 global PGP_KEY
 if private_key:
  import pgpy
  PGP_KEY,_=pgpy.PGPKey.from_file(private_key)
  key=str(PGP_KEY.fingerprint)
 stage=ROOT/'build'/'stage'
 if stage.exists():shutil.rmtree(stage)
 (stage/'usr/bin').mkdir(parents=True)
 (stage/'usr/lib/apkm').mkdir(parents=True)
 shutil.copy(ROOT/'src/apkm.py',stage/'usr/lib/apkm/apkm.py')
 shutil.copy(ROOT/'src/fdroid.gpg',stage/'usr/lib/apkm/fdroid.gpg')
 for command in ['apkm','apkg']:
  path=stage/'usr/bin'/command
  path.write_text('#!/usr/bin/python3\nimport sys\nsys.path.insert(0,"/usr/lib/apkm")\nfrom apkm import main\nsys.exit(main(program="'+command+'"))\n')
  path.chmod(0o755)
  dest=stage/'usr/share/man/man1'/f'{command}.1.gz';dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_bytes(gzip.compress((ROOT/'docs'/f'{command}.1').read_bytes(),mtime=0))
 (stage/'usr/share/doc/apkm').mkdir(parents=True)
 shutil.copy(ROOT/'LICENSE',stage/'usr/share/doc/apkm/copyright')
 shutil.copy(ROOT/'README.md',stage/'usr/share/doc/apkm/README.md')
 public=SITE/'keys';public.mkdir(parents=True,exist_ok=True)
 if PGP_KEY is not None:
  (public/'apkm.gpg').write_bytes(bytes(PGP_KEY.pubkey))
 else:
  with (public/'apkm.gpg').open('wb') as f:call(['gpg','--export',key],stdout=f)
 (public/'FINGERPRINT.txt').write_text(key+'\n')
 shutil.copy(public/'apkm.gpg',stage/'usr/share/apkm-keyring.gpg')
 (stage/'DEBIAN').mkdir()
 (stage/'DEBIAN/control').write_text('Package: apkm\nVersion: '+VER+'-1\nArchitecture: all\nMaintainer: APKM Project <apkm@example.invalid>\nDepends: python3 (>= 3.9), adb, gpgv\nSection: utils\nPriority: optional\nDescription: Signed APK repository client and Android installer\n Provides apkm and apkg commands for ADB and Android host root installation.\n')
 deb=ROOT/'build'/f'apkm_{VER}-1_all.deb';call(['dpkg-deb','--root-owner-group','--build',str(stage),str(deb)])
 for arch in ['amd64','arm64']:
  dest=SITE/'debian'/arch;dest.mkdir(parents=True,exist_ok=True);shutil.copy(deb,dest/deb.name)
  scan=call(['dpkg-scanpackages','--multiversion','.','/dev/null'],cwd=dest,stdout=subprocess.PIPE).stdout
  (dest/'Packages').write_bytes(scan);(dest/'Packages.gz').write_bytes(gzip.compress(scan,mtime=0))
  release='Origin: APKM\nLabel: APKM\nSuite: stable\nArchitectures: '+arch+' all\nDate: '+time.strftime('%a, %d %b %Y %H:%M:%S +0000',time.gmtime())+'\nSHA256:\n'
  for n in ['Packages','Packages.gz']:
   b=(dest/n).read_bytes();release+=f' {hashlib.sha256(b).hexdigest()} {len(b)} {n}\n'
  (dest/'Release').write_text(release)
  if PGP_KEY is not None:
   import pgpy
   message=pgpy.PGPMessage.new(release,cleartext=True)
   message |= PGP_KEY.sign(message)
   (dest/'InRelease').write_text(str(message))
   (dest/'Release.gpg').write_bytes(bytes(PGP_KEY.sign((dest/'Release').read_bytes())))
  else:
   call(['gpg','--batch','--yes','--local-user',key,'--clearsign','--output',str(dest/'InRelease'),str(dest/'Release')])
   call(['gpg','--batch','--yes','--local-user',key,'--detach-sign','--output',str(dest/'Release.gpg'),str(dest/'Release')])
 # Pacman package archive and database use the documented ALPM tar formats.
 pkg=ROOT/'build'/f'apkm-{VER}-1-any.pkg.tar.zst'
 raw=ROOT/'build'/'arch.tar'
 files=[]
 with tarfile.open(raw,'w',format=tarfile.PAX_FORMAT) as t:
  info=f'pkgname = apkm\npkgbase = apkm\npkgver = {VER}-1\npkgdesc = Signed APK repository client and Android installer\nurl = https://villager1314.github.io/repo/\nbuilddate = {int(time.time())}\npackager = APKM Project\nsize = '+str(sum(p.stat().st_size for p in stage.rglob('*') if p.is_file() and 'DEBIAN' not in p.parts))+'\narch = any\nlicense = MIT\ndepend = python\ndepend = android-tools\ndepend = gnupg\n'
  b=info.encode();ti=tarfile.TarInfo('.PKGINFO');ti.size=len(b);ti.uid=ti.gid=0;t.addfile(ti,io.BytesIO(b))
  for p in sorted((stage/'usr').rglob('*')):
   if p.is_file():
    n=p.relative_to(stage).as_posix();files.append(n)
    ti=t.gettarinfo(str(p),n);ti.uid=ti.gid=0;ti.uname=ti.gname='root'
    with p.open('rb') as f:t.addfile(ti,f)
 call(['zstd','-q','-f',str(raw),'-o',str(pkg)]);sign(pkg,key)
 binary=pkg.read_bytes();sig=base64.b64encode(Path(str(pkg)+'.sig').read_bytes()).decode()
 fields={'FILENAME':[pkg.name],'NAME':['apkm'],'BASE':['apkm'],'VERSION':[VER+'-1'],'DESC':['Signed APK repository client and Android installer'],'CSIZE':[str(len(binary))],'ISIZE':[str(sum(p.stat().st_size for p in stage.rglob('*') if p.is_file() and 'DEBIAN' not in p.parts))],'SHA256SUM':[hashlib.sha256(binary).hexdigest()],'PGPSIG':[sig],'URL':['https://villager1314.github.io/repo/'],'LICENSE':['MIT'],'ARCH':['any'],'BUILDDATE':[str(int(time.time()))],'PACKAGER':['APKM Project'],'DEPENDS':['python','android-tools','gnupg']}
 desc=''.join('%'+k+'%\n'+'\n'.join(v)+'\n\n' for k,v in fields.items()).encode()
 for arch in ['x86_64','aarch64']:
  dest=SITE/'arch'/arch;dest.mkdir(parents=True,exist_ok=True)
  shutil.copy(pkg,dest/pkg.name);shutil.copy(str(pkg)+'.sig',dest/(pkg.name+'.sig'))
  for suffix,include_files in [('db',False),('files',True)]:
   db=dest/f'apkm.{suffix}.tar.gz'
   with tarfile.open(db,'w:gz') as t:
    content={'desc':desc}
    if include_files:content['files']=('%FILES%\n'+'\n'.join(files)+'\n').encode()
    for n,b in content.items():
     ti=tarfile.TarInfo(f'apkm-{VER}-1/{n}');ti.size=len(b);t.addfile(ti,io.BytesIO(b))
   sign(db,key)
   # Actual copies, not symlinks: GitHub Pages must serve these URLs directly.
   shutil.copy(db,dest/f'apkm.{suffix}');shutil.copy(str(db)+'.sig',dest/f'apkm.{suffix}.sig')
 index=SITE/'android/index.json'
 if not index.exists():index.write_text(json.dumps({'schema_version':1,'revision':1,'packages':[]},indent=2)+'\n')
 sign(index,key)
 (SITE/'.nojekyll').touch()
 print('Built:',SITE)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--key',help='GPG signing fingerprint');p.add_argument('--private-key',help='Local unencrypted OpenPGP key; requires PGPy on build host');a=p.parse_args()
 if not a.key and not a.private_key:p.error('--key or --private-key required')
 build(a.key,a.private_key)
