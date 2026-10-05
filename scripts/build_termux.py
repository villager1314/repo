#!/usr/bin/env python3
"""Build a Termux-only, architecture-independent deb and signed flat APT repository."""
import argparse,gzip,hashlib,shutil,subprocess,time
from pathlib import Path
import build as signing
ROOT=Path(__file__).resolve().parents[1]
PREFIX=Path('/data/data/com.termux/files/usr')
VERSION='0.3.0-1'
def build_termux(key=None,private_key=None):
 if private_key:
  import pgpy
  signing.PGP_KEY,_=pgpy.PGPKey.from_file(private_key)
  key=str(signing.PGP_KEY.fingerprint)
 stage=ROOT/'build/termux-stage'
 if stage.exists():shutil.rmtree(stage)
 target=stage/PREFIX.relative_to('/')
 (target/'bin').mkdir(parents=True)
 (target/'lib/apkm').mkdir(parents=True)
 shutil.copy(ROOT/'src/apkm.py',target/'lib/apkm/apkm.py')
 shutil.copy(ROOT/'src/fdroid.gpg',target/'lib/apkm/fdroid.gpg')
 for command in ['apkm','apkg']:
  path=target/'bin'/command
  path.write_text(f'#!{PREFIX}/bin/python\nimport sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parents[1]/"lib/apkm"))\nfrom apkm import main\nsys.exit(main(program="{command}"))\n')
  path.chmod(0o755)
  man=target/'share/man/man1'/f'{command}.1.gz';man.parent.mkdir(parents=True,exist_ok=True)
  man.write_bytes(gzip.compress((ROOT/'docs'/f'{command}.1').read_bytes(),mtime=0))
 (target/'share/doc/apkm').mkdir(parents=True)
 shutil.copy(ROOT/'docs/TERMUX.md',target/'share/doc/apkm/README.md')
 shutil.copy(ROOT/'LICENSE',target/'share/doc/apkm/copyright')
 shutil.copy(ROOT/'site/keys/apkm.gpg',target/'share/apkm-keyring.gpg')
 (stage/'DEBIAN').mkdir()
 (stage/'DEBIAN/control').write_text(f'Package: apkm\nVersion: {VERSION}\nArchitecture: all\nMaintainer: APKM Project <apkm@example.invalid>\nDepends: python (>= 3.9), android-tools, gpgv\nSuggests: man\nSection: utils\nPriority: optional\nHomepage: https://github.com/villager1314/repo\nDescription: APK repository client and Android installer for Termux\n Provides apkm and apkg, installed under the standard com.termux prefix.\n')
 dest=ROOT/'site/termux';dest.mkdir(parents=True,exist_ok=True)
 package=dest/f'apkm_{VERSION}_all.deb'
 signing.call(['dpkg-deb','--root-owner-group','--build',str(stage),str(package)])
 scan=signing.call(['dpkg-scanpackages','--multiversion','.','/dev/null'],cwd=dest,stdout=subprocess.PIPE).stdout
 (dest/'Packages').write_bytes(scan);(dest/'Packages.gz').write_bytes(gzip.compress(scan,mtime=0))
 release='Origin: APKM-Termux\nLabel: APKM-Termux\nSuite: stable\nArchitectures: aarch64 x86_64 all\nDate: '+time.strftime('%a, %d %b %Y %H:%M:%S +0000',time.gmtime())+'\nSHA256:\n'
 for n in ['Packages','Packages.gz']:
  b=(dest/n).read_bytes();release+=f' {hashlib.sha256(b).hexdigest()} {len(b)} {n}\n'
 (dest/'Release').write_text(release)
 if signing.PGP_KEY is not None:
  import pgpy
  message=pgpy.PGPMessage.new(release,cleartext=True);message|=signing.PGP_KEY.sign(message)
  (dest/'InRelease').write_text(str(message))
  (dest/'Release.gpg').write_bytes(bytes(signing.PGP_KEY.sign((dest/'Release').read_bytes())))
 else:
  signing.call(['gpg','--batch','--yes','--local-user',key,'--clearsign','--output',str(dest/'InRelease'),str(dest/'Release')])
  signing.call(['gpg','--batch','--yes','--local-user',key,'--detach-sign','--output',str(dest/'Release.gpg'),str(dest/'Release')])
 shutil.copy(ROOT/'docs/TERMUX.md',ROOT/'site/TERMUX.md')
 print('Built Termux repository:',dest)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--key');p.add_argument('--private-key');a=p.parse_args()
 if not a.key and not a.private_key:p.error('--key or --private-key required')
 build_termux(a.key,a.private_key)
