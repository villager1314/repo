#!/usr/bin/env python3
import gzip,hashlib,io,json,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SITE=ROOT/'site';KEY=SITE/'keys/apkm.gpg'
def verify(sig,file):subprocess.run(['gpgv','--keyring',str(KEY),str(sig),str(file)],check=True,capture_output=True)
for arch in ['amd64','arm64']:
 d=SITE/'debian'/arch
 verify(d/'Release.gpg',d/'Release')
 subprocess.run(['gpgv','--keyring',str(KEY),str(d/'InRelease')],check=True,capture_output=True)
 assert gzip.decompress((d/'Packages.gz').read_bytes())==(d/'Packages').read_bytes()
 package=d/'apkm_0.3.1-1_all.deb'; fields=dict(line.split(': ',1) for line in (d/'Packages').read_text().splitlines() if ': ' in line)
 assert fields['Architecture']=='all' and fields['Package']=='apkm'
 assert fields['SHA256']==hashlib.sha256(package.read_bytes()).hexdigest()
 assert fields['Filename']=='./'+package.name
 subprocess.run(['dpkg-deb','--info',str(package)],check=True,stdout=subprocess.DEVNULL)
for arch in ['x86_64','aarch64']:
 d=SITE/'arch'/arch;pkg=d/'apkm-0.3.1-1-any.pkg.tar.zst'
 verify(Path(str(pkg)+'.sig'),pkg)
 for suffix in ['db','files']:
  path=d/f'apkm.{suffix}'
  verify(Path(str(path)+'.sig'),path)
  with tarfile.open(path) as t:
   text=t.extractfile('apkm-0.3.1-1/desc').read().decode()
   assert '%NAME%\napkm\n' in text and '%ARCH%\nany\n' in text
   assert hashlib.sha256(pkg.read_bytes()).hexdigest() in text
 data=subprocess.run(['zstd','-d','-c',str(pkg)],check=True,capture_output=True).stdout
 with tarfile.open(fileobj=io.BytesIO(data)) as t:
  assert 'usr/bin/apkm' in t.getnames() and 'usr/bin/apkg' in t.getnames()
  assert 'arch = any' in t.extractfile('.PKGINFO').read().decode()
verify(SITE/'android/index.json.sig',SITE/'android/index.json')
assert json.loads((SITE/'android/index.json').read_text())['packages']==[]
# Exercise APT itself in an isolated state/cache using local file repositories.
for arch in ['amd64','arm64']:
 with tempfile.TemporaryDirectory(prefix='apkm-apt-') as temp:
  p=Path(temp);(p/'lists/partial').mkdir(parents=True);(p/'cache/archives/partial').mkdir(parents=True);(p/'empty').mkdir();(p/'status').touch()
  (p/'sources.list').write_text(f'deb [arch={arch} signed-by={KEY}] file:{SITE}/debian/{arch}/ ./\n')
  options=['-o',f'Dir::Etc::sourcelist={p}/sources.list','-o',f'Dir::Etc::sourceparts={p}/empty','-o',f'Dir::State::lists={p}/lists','-o',f'Dir::State::status={p}/status','-o',f'Dir::Cache={p}/cache','-o',f'APT::Architecture={arch}','-o','APT::Sandbox::User=root','-o','Dir::Etc::main=/dev/null','-o',f'Dir::Etc::parts={p}/empty']
  r=subprocess.run(['apt-get']+options+['update'],capture_output=True,text=True)
  if r.returncode or 'Failed to fetch' in r.stderr or 'NO_PUBKEY' in r.stderr:
   raise RuntimeError(r.stdout+r.stderr)
  r=subprocess.run(['apt-cache']+options+['show','apkm'],check=True,capture_output=True,text=True)
  assert 'Package: apkm' in r.stdout and 'Architecture: all' in r.stdout
print('PASS: four repositories, signatures, archive metadata, and isolated APT amd64/arm64 index loading')
