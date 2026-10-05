import gzip,hashlib,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PREFIX=Path('data/data/com.termux/files/usr')
class Termux(unittest.TestCase):
 def test_package_layout_dependencies_and_launch(self):
  deb=ROOT/'site/termux/apkm_0.3.0-1_all.deb'
  control=subprocess.run(['dpkg-deb','-f',str(deb)],check=True,capture_output=True,text=True).stdout
  self.assertIn('Architecture: all',control)
  self.assertIn('Depends: python (>= 3.9), android-tools, gpgv',control)
  with tempfile.TemporaryDirectory() as d:
   subprocess.run(['dpkg-deb','-x',str(deb),d],check=True)
   prefix=Path(d)/PREFIX
   self.assertFalse((Path(d)/'usr').exists())
   for name in ['apkm','apkg']:
    launcher=prefix/'bin'/name
    self.assertTrue(launcher.read_text().startswith('#!/data/data/com.termux/files/usr/bin/python\n'))
    result=subprocess.run([sys.executable,str(launcher),'--help'],check=True,capture_output=True,text=True)
    self.assertIn('usage: '+name,result.stdout)
    self.assertIn('.TH '+name.upper(),gzip.decompress((prefix/'share/man/man1'/f'{name}.1.gz').read_bytes()).decode())
   self.assertEqual((prefix/'share/apkm-keyring.gpg').read_bytes(),(ROOT/'site/keys/apkm.gpg').read_bytes())
 def test_signed_apt_index_aarch64_x86_64(self):
  site=ROOT/'site/termux';key=ROOT/'site/keys/apkm.gpg'
  subprocess.run(['gpgv','--keyring',str(key),str(site/'InRelease')],check=True,capture_output=True)
  for arch in ['aarch64','x86_64']:
   with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'lists/partial').mkdir(parents=True);(p/'cache/archives/partial').mkdir(parents=True);(p/'empty').mkdir();(p/'status').touch()
    (p/'sources.list').write_text(f'deb [arch={arch} signed-by={key}] file:{site}/ ./\n')
    options=['-o',f'Dir::Etc::sourcelist={p}/sources.list','-o',f'Dir::Etc::sourceparts={p}/empty','-o',f'Dir::State::lists={p}/lists','-o',f'Dir::State::status={p}/status','-o',f'Dir::Cache={p}/cache','-o',f'APT::Architecture={arch}','-o','APT::Sandbox::User=root','-o','Dir::Etc::main=/dev/null','-o',f'Dir::Etc::parts={p}/empty']
    r=subprocess.run(['apt-get']+options+['update'],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    self.assertNotIn('Failed to fetch',r.stderr)
    r=subprocess.run(['apt-cache']+options+['show','apkm'],check=True,capture_output=True,text=True)
    self.assertIn('Depends: python (>= 3.9), android-tools, gpgv',r.stdout)
    self.assertIn('Architecture: all',r.stdout)
if __name__=='__main__':unittest.main()
